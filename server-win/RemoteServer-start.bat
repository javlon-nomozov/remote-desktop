@echo off
chcp 65001 >nul
title Remote Server
echo ================================================
echo   Remote Server
echo ================================================
echo.
echo Backend manzilini kiriting (unique kod orqali ulanish uchun),
echo masalan: wss://xxx.up.railway.app
echo Bo'sh qoldirsangiz - LAN (IP) rejimida ishlaydi.
echo.
set /p RELAY="Backend manzili: "
echo.
if "%RELAY%"=="" (
  "%~dp0RemoteServer.exe"
) else (
  "%~dp0RemoteServer.exe" --relay %RELAY%
)
echo.
echo Dastur to'xtadi. Yopish uchun istalgan tugmani bosing.
pause >nul
