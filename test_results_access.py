#!/usr/bin/env python3
"""
测试结果文件访问
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_results_access():
    """测试结果文件是否可以通过HTTP访问"""
    
    # 测试一个已存在的结果文件
    test_paths = [
        "/results/user-001/1f540b58-937e-4578-986a-44b67065001f/segmentation_results.json",
        "/results/user-001/1f540b58-937e-4578-986a-44b67065001f/visualization.jpg",
    ]
    
    print("🔍 测试结果文件访问...")
    print(f"服务器地址: {BASE_URL}\n")
    
    for path in test_paths:
        url = BASE_URL + path
        print(f"测试: {url}")
        
        try:
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                print(f"  ✅ 成功! 状态码: {response.status_code}")
                if path.endswith('.json'):
                    data = response.json()
                    print(f"  📊 找到 {data.get('total_cells', 0)} 个细胞")
                elif path.endswith('.jpg'):
                    print(f"  🖼️  图像大小: {len(response.content)} 字节")
            else:
                print(f"  ❌ 失败! 状态码: {response.status_code}")
                print(f"  响应: {response.text[:200]}")
                
        except requests.exceptions.ConnectionError:
            print(f"  ❌ 无法连接到服务器! 请确保服务器正在运行")
            print(f"  提示: 运行 'python main.py' 启动服务器")
            break
        except Exception as e:
            print(f"  ❌ 错误: {e}")
        
        print()

if __name__ == "__main__":
    test_results_access()

