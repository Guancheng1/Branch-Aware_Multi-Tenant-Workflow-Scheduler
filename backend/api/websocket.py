"""
WebSocket support - Real-time progress updates
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import json
import logging

from backend.core.scheduler import scheduler
from backend.services.workflow_manager import workflow_manager

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket connection manager"""
    
    def __init__(self):
        # Store active connections: user_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
        # Job subscriptions: job_id -> set of websockets
        self.job_subscriptions: Dict[str, Set[WebSocket]] = {}
        
        # Workflow subscriptions: workflow_id -> set of websockets
        self.workflow_subscriptions: Dict[str, Set[WebSocket]] = {}
        
        # Broadcast task
        self.broadcast_task = None
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept new connection"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        
        self.active_connections[user_id].add(websocket)
        
        logger.info(f"WebSocket connected for user {user_id}")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Disconnect"""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        # Clean up subscriptions
        for job_id, sockets in list(self.job_subscriptions.items()):
            sockets.discard(websocket)
            if not sockets:
                del self.job_subscriptions[job_id]
        
        for workflow_id, sockets in list(self.workflow_subscriptions.items()):
            sockets.discard(websocket)
            if not sockets:
                del self.workflow_subscriptions[workflow_id]
        
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    def subscribe_job(self, websocket: WebSocket, job_id: str):
        """Subscribe to job updates"""
        if job_id not in self.job_subscriptions:
            self.job_subscriptions[job_id] = set()
        
        self.job_subscriptions[job_id].add(websocket)
    
    def subscribe_workflow(self, websocket: WebSocket, workflow_id: str):
        """Subscribe to workflow updates"""
        if workflow_id not in self.workflow_subscriptions:
            self.workflow_subscriptions[workflow_id] = set()
        
        self.workflow_subscriptions[workflow_id].add(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Send personal message"""
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    
    async def broadcast_to_user(self, message: str, user_id: str):
        """Broadcast to all user connections"""
        if user_id not in self.active_connections:
            return
        
        dead_sockets = set()
        for websocket in self.active_connections[user_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_id}: {e}")
                dead_sockets.add(websocket)
        
        # Clean up dead connections
        for socket in dead_sockets:
            self.disconnect(socket, user_id)
    
    async def broadcast_job_update(self, job_id: str):
        """Broadcast job update"""
        if job_id not in self.job_subscriptions:
            return
        
        job = scheduler.get_job(job_id)
        if not job:
            return
        
        message = json.dumps({
            "type": "job_update",
            "job_id": job_id,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "tiles_processed": job.tiles_processed,
            "tiles_total": job.tiles_total,
            "current_message": job.current_message,
            "error": job.error
        })
        
        dead_sockets = set()
        for websocket in self.job_subscriptions[job_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting job update: {e}")
                dead_sockets.add(websocket)
        
        # Clean up dead connections
        for socket in dead_sockets:
            self.job_subscriptions[job_id].discard(socket)
    
    async def broadcast_workflow_update(self, workflow_id: str):
        """Broadcast workflow update"""
        if workflow_id not in self.workflow_subscriptions:
            return
        
        progress = workflow_manager.get_workflow_progress(workflow_id)
        if not progress:
            return
        
        message = json.dumps({
            "type": "workflow_update",
            "workflow_id": workflow_id,
            "status": progress.status,
            "progress_percent": progress.progress_percent,
            "jobs": [
                {
                    "job_id": j.job_id,
                    "status": j.status,
                    "progress_percent": j.progress_percent,
                    "current_message": j.current_message
                }
                for j in progress.jobs
            ]
        })
        
        dead_sockets = set()
        for websocket in self.workflow_subscriptions[workflow_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting workflow update: {e}")
                dead_sockets.add(websocket)
        
        # Clean up dead connections
        for socket in dead_sockets:
            self.workflow_subscriptions[workflow_id].discard(socket)
    
    async def start_broadcasting(self):
        """Start periodic broadcast task"""
        if self.broadcast_task is None:
            self.broadcast_task = asyncio.create_task(self._broadcast_loop())
    
    async def stop_broadcasting(self):
        """Stop broadcast task"""
        if self.broadcast_task:
            self.broadcast_task.cancel()
            try:
                await self.broadcast_task
            except asyncio.CancelledError:
                pass
    
    async def _broadcast_loop(self):
        """Periodic broadcast updates"""
        while True:
            try:
                # Broadcast all subscribed job updates
                for job_id in list(self.job_subscriptions.keys()):
                    await self.broadcast_job_update(job_id)
                
                # Broadcast all subscribed workflow updates
                for workflow_id in list(self.workflow_subscriptions.keys()):
                    await self.broadcast_workflow_update(workflow_id)
                
                await asyncio.sleep(1)  # Update every second
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in broadcast loop: {e}", exc_info=True)
                await asyncio.sleep(1)


# Global connection manager
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint
    
    Clients can send messages to subscribe to specific jobs or workflows:
    {"action": "subscribe_job", "job_id": "xxx"}
    {"action": "subscribe_workflow", "workflow_id": "xxx"}
    """
    await manager.connect(websocket, user_id)
    
    try:
        while True:
            # Receive client messages
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                action = message.get("action")
                
                if action == "subscribe_job":
                    job_id = message.get("job_id")
                    if job_id:
                        # Verify permissions
                        job = scheduler.get_job(job_id)
                        if job and job.user_id == user_id:
                            manager.subscribe_job(websocket, job_id)
                            await manager.send_personal_message(
                                json.dumps({"status": "subscribed", "job_id": job_id}),
                                websocket
                            )
                            # Send current status immediately
                            await manager.broadcast_job_update(job_id)
                
                elif action == "subscribe_workflow":
                    workflow_id = message.get("workflow_id")
                    if workflow_id:
                        # Verify permissions
                        workflow = workflow_manager.get_workflow(workflow_id)
                        if workflow and workflow.user_id == user_id:
                            manager.subscribe_workflow(websocket, workflow_id)
                            await manager.send_personal_message(
                                json.dumps({"status": "subscribed", "workflow_id": workflow_id}),
                                websocket
                            )
                            # Send current status immediately
                            await manager.broadcast_workflow_update(workflow_id)
                
                elif action == "ping":
                    await manager.send_personal_message(
                        json.dumps({"type": "pong"}),
                        websocket
                    )
            
            except json.JSONDecodeError:
                await manager.send_personal_message(
                    json.dumps({"error": "Invalid JSON"}),
                    websocket
                )
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}", exc_info=True)
        manager.disconnect(websocket, user_id)


