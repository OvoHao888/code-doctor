@echo off
REM 启动后端服务（Windows 本地运行）
REM 必须设置 UTF-8：Windows 控制台默认 GBK，中文/emoji 日志会触发 UnicodeEncodeError

cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] 创建虚拟环境...
    python -m venv .venv
    echo [2/2] 安装依赖...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo 启动后浏览器打开: http://localhost:8000
echo （前端页面由后端直接提供，只需这一个地址）
REM 绑定 127.0.0.1 而非 0.0.0.0：接口无鉴权，不应暴露到局域网
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000

pause
