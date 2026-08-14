@echo off
cd /d "%~dp0"
echo Installing required packages...
python -m pip install -r requirements.txt
echo.
echo Starting DR Failover Simulator Engine...
start "DR Failover Simulator Server" cmd /k python app.py
echo Waiting for server to start...
timeout /t 4 /nobreak >nul
start http://127.0.0.1:5002
echo.
echo The dashboard should now be open in your browser.
echo A separate black window is running the server and the failover engine - keep it open while using the app.
echo You can close THIS window now.
pause
