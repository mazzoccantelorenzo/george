.PHONY: install icon lint build package release clean

APP_NAME = George
REPO = mazzoccantelorenzo/george
PYTHON := $(shell if /Library/Developer/CommandLineTools/usr/bin/python3 -c "import PyQt6" >/dev/null 2>&1; then echo /Library/Developer/CommandLineTools/usr/bin/python3; else echo python3; fi)
ICON_PNG = icon.png
ICON_ICNS = app_icon.icns
SOURCES = app.py window.py pdf_viewer.py postits.py postit_text.py document_editor.py vault.py tools.py settings.py resources.py theme.py ai_panel.py chat_renderer.py chat_history.py reading_notes.py file_permissions.py permission_hook.py updater.py

install:
	@echo "Installando le dipendenze..."
	$(PYTHON) -m pip install PyQt6 PyQt6-WebEngine==6.10.0 PyMuPDF pyinstaller mypy ruff

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
	$(PYTHON) -m mypy $(SOURCES)
	$(PYTHON) -m ruff check $(SOURCES) --ignore BLE001,S110,SIM102,UP045,I001

build: install lint icon
	@echo "Compilando l'applicazione nativa Mac..."
	$(PYTHON) -m PyInstaller --windowed --noconfirm --icon=$(ICON_ICNS) --add-data "icon_fixed.png:." --add-data "icons:icons" --add-data "chat_assets:chat_assets" --name=$(APP_NAME) app.py
	@echo "Rimozione attributi estesi e firma ad-hoc per Apple Silicon..."
	xattr -cr dist/$(APP_NAME).app
	codesign --force --deep --sign - dist/$(APP_NAME).app
	@echo "Fatto! Sposto l'app sulla tua Scrivania per accesso immediato..."
	rm -rf ~/Desktop/$(APP_NAME).app
	cp -R dist/$(APP_NAME).app ~/Desktop/
	@echo "Tutto pronto, divertiti!"

package: build
	@echo "Creazione pacchetto George.zip per l'auto-updater (preservando symlink macOS)..."
	rm -f dist/$(APP_NAME).zip dist/$(APP_NAME)-Installer.dmg
	ditto -c -k --sequesterRsrc --keepParent dist/$(APP_NAME).app dist/$(APP_NAME).zip
	@echo "Creazione installer DMG user-friendly per non-sviluppatori..."
	rm -rf dist/dmg_staging
	mkdir -p dist/dmg_staging
	cp -R dist/$(APP_NAME).app dist/dmg_staging/
	ln -s /Applications dist/dmg_staging/Applications
	printf '#!/bin/bash\nset -e\nDIR="$$(cd "$$(dirname "$$0")" && pwd)"\necho "Installazione di George in /Applications in corso..."\nrm -rf /Applications/George.app\ncp -R "$$DIR/George.app" /Applications/George.app\nxattr -cr /Applications/George.app 2>/dev/null || true\ncodesign --force --deep --sign - /Applications/George.app 2>/dev/null || true\necho "Fatto! Avvio di George..."\nopen /Applications/George.app\n' > "dist/dmg_staging/Installa e Apri George.command"
	chmod +x "dist/dmg_staging/Installa e Apri George.command"
	hdiutil create -volname "$(APP_NAME) Installer" -srcfolder dist/dmg_staging -ov -format UDZO dist/$(APP_NAME)-Installer.dmg
	rm -rf dist/dmg_staging
	@echo "Pacchetti pronti in dist/$(APP_NAME).zip e dist/$(APP_NAME)-Installer.dmg"

# Uso: make release VERSION=v12.1 NOTES="Novita della versione"
release: package
	@if [ -z "$(VERSION)" ]; then echo "Errore: specifica VERSION (es. make release VERSION=v12.1 NOTES='...')"; exit 1; fi
	@echo "Verifica repository GitHub $(REPO)..."
	@gh repo view "$(REPO)" >/dev/null 2>&1 || gh repo create "$(REPO)" --public --description "George — PDF Reader & AI Workspace (macOS & Windows)"
	@git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$(REPO).git"
	@echo "Sincronizzazione codice con GitHub (per attivare la build automatica Windows su GitHub Actions)..."
	@git push -u origin HEAD || true
	@echo "Pubblicazione della release $(VERSION) su GitHub ($(REPO))..."
	gh release create "$(VERSION)" dist/$(APP_NAME).zip dist/$(APP_NAME)-Installer.dmg --repo "$(REPO)" --title "George $(VERSION)" --notes "$(or $(NOTES),Aggiornamento di George $(VERSION))"
	@echo "Release $(VERSION) pubblicata! GitHub Actions sta compilando e allegando in automatico George-Windows.zip."

clean:
	rm -rf build dist $(APP_NAME).spec MyIcon.iconset $(ICON_ICNS)

