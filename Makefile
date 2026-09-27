.PHONY: install icon build clean

APP_NAME = George
ICON_PNG = icon.png
ICON_ICNS = app_icon.icns

install:
	@echo "Installando le dipendenze..."
	python3 -m pip install PyQt6 PyMuPDF pyinstaller mypy ruff

# Script per convertire il PNG in una vera icona ICNS nativa per Mac
icon:
	@echo "Convertendo l'icona per macOS..."
	mkdir -p MyIcon.iconset
	sips -z 16 16     icon_fixed.png --out MyIcon.iconset/icon_16x16.png
	sips -z 32 32     icon_fixed.png --out MyIcon.iconset/icon_16x16@2x.png
	sips -z 32 32     icon_fixed.png --out MyIcon.iconset/icon_32x32.png
	sips -z 64 64     icon_fixed.png --out MyIcon.iconset/icon_32x32@2x.png
	sips -z 128 128   icon_fixed.png --out MyIcon.iconset/icon_128x128.png
	sips -z 256 256   icon_fixed.png --out MyIcon.iconset/icon_128x128@2x.png
	sips -z 256 256   icon_fixed.png --out MyIcon.iconset/icon_256x256.png
	sips -z 512 512   icon_fixed.png --out MyIcon.iconset/icon_256x256@2x.png
	sips -z 512 512   icon_fixed.png --out MyIcon.iconset/icon_512x512.png
	sips -z 1024 1024 icon_fixed.png --out MyIcon.iconset/icon_512x512@2x.png
	iconutil -c icns MyIcon.iconset -o $(ICON_ICNS)
	rm -R MyIcon.iconset

lint:
	@echo "Verifica tipi e sintassi super rigida in corso..."
	mypy app.py
	ruff check app.py --ignore BLE001,S110,SIM102,UP045,I001

build: install lint icon
	@echo "Compilando l'applicazione nativa Mac..."
	pyinstaller --windowed --noconfirm --icon=$(ICON_ICNS) --add-data "icon_fixed.png:." --add-data "icons:icons" --name=$(APP_NAME) app.py
	@echo "Fatto! Sposto l'app sulla tua Scrivania per accesso immediato..."
	cp -R dist/George.app ~/Desktop/
	@echo "Tutto pronto, divertiti!"

clean:
	rm -rf build dist $(APP_NAME).spec MyIcon.iconset $(ICON_ICNS)
