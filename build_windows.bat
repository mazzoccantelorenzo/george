@echo off
setlocal
echo ===================================================
echo   Build di George per Windows
echo ===================================================

python -m pip install --upgrade pip
python -m pip install PyQt6 PyQt6-WebEngine==6.10.0 PyMuPDF pyinstaller pillow

echo Conversione icona in formato .ico...
python -c "from PIL import Image; img = Image.open('icon_fixed.png'); img.save('app_icon.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"

echo Compilazione di George.exe con PyInstaller...
python -m PyInstaller --windowed --noconfirm --icon=app_icon.ico --add-data "icon_fixed.png;." --add-data "icons;icons" --add-data "chat_assets;chat_assets" --name=George app.py

echo Creazione archivio dist\George-Windows.zip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\George' -DestinationPath 'dist\George-Windows.zip' -Force"

echo Fatto! Il pacchetto per Windows si trova in dist\George-Windows.zip
