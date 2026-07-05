#!/bin/bash
# Setup-script Raspberry Pi 5 (Linux) — Project Loods WP3
#
# Voer uit op een vers geflashte Raspberry Pi OS 64-bit Bookworm (SSH aan):
#   chmod +x setup_linux_rpi5.sh
#   ./setup_linux_rpi5.sh B          # of "A" — welk device dit fysiek is
#
# Gebaseerd op de handmatige stappen die op RPi A (rasp1) zijn doorlopen
# (2026-07-04), gebundeld zodat RPi B (rasp2) in één keer op dezelfde
# configuratie gebracht kan worden.

set -e

DEVICE="${1:-B}"
REPO_URL="https://github.com/Hersenpap206/MIT2026.git"
REPO_DIR="$HOME/MIT2026"
MODEL_DIR="$HOME/modellen"
VOSK_MODEL="vosk-model-small-nl-0.22"

stap()  { echo -e "\n\033[36m=== $1 ===\033[0m"; }
ok()    { echo -e "\033[32mOK: $1\033[0m"; }
info()  { echo -e "   $1"; }

if [[ "$DEVICE" != "A" && "$DEVICE" != "B" ]]; then
    echo "Gebruik: ./setup_linux_rpi5.sh [A|B]"
    exit 1
fi

stap "1. Systeempackages installeren (i2c-tools, python3-smbus, libportaudio2)"
sudo apt update
sudo apt install -y python3-smbus i2c-tools libportaudio2 unzip
ok "Systeempackages geinstalleerd"

stap "2. I2C inschakelen"
if lsmod | grep -q i2c_dev; then
    ok "I2C al ingeschakeld — sla over"
else
    sudo raspi-config nonint do_i2c 0
    info "I2C ingeschakeld — een reboot is nodig voordat i2cdetect werkt"
    REBOOT_NODIG=1
fi

stap "3. Repo clonen/updaten (~/MIT2026)"
if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" pull
    ok "Repo bijgewerkt"
else
    git clone "$REPO_URL" "$REPO_DIR"
    ok "Repo gecloned"
fi

stap "4. Python packages installeren"
pip install -r "$REPO_DIR/requirements_linux.txt" --break-system-packages
ok "Packages geinstalleerd"

stap "5. Vosk NL-model downloaden"
mkdir -p "$MODEL_DIR"
if [ -d "$MODEL_DIR/$VOSK_MODEL" ]; then
    ok "Vosk model al aanwezig — sla over"
else
    cd "$MODEL_DIR"
    wget -q "https://alphacephei.com/vosk/models/${VOSK_MODEL}.zip"
    unzip -q "${VOSK_MODEL}.zip"
    rm "${VOSK_MODEL}.zip"
    cd - > /dev/null
    ok "Vosk model gedownload naar $MODEL_DIR/$VOSK_MODEL"
fi

stap "6. Whisper tiny model downloaden (default cache)"
python3 -c "import whisper; whisper.load_model('tiny')"
ok "Whisper tiny model aanwezig"

stap "7. Omgevingsvariabelen persistent zetten (~/.bashrc)"
BASHRC="$HOME/.bashrc"
set_env_line() {
    local key="$1" val="$2"
    if grep -q "^export ${key}=" "$BASHRC" 2>/dev/null; then
        sed -i "s|^export ${key}=.*|export ${key}=\"${val}\"|" "$BASHRC"
    else
        echo "export ${key}=\"${val}\"" >> "$BASHRC"
    fi
}
set_env_line "LOODS_DEVICE" "$DEVICE"
set_env_line "LOODS_OPERATOR" "wim"
set_env_line "LOODS_SW_VERSION" "v1.0-dev"
ok "LOODS_DEVICE=$DEVICE, LOODS_OPERATOR, LOODS_SW_VERSION toegevoegd aan ~/.bashrc"

stap "8. Verificatie"
python3 - "$REPO_DIR" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import smbus2, gpiozero, sounddevice, soundfile, whisper, vosk
import azure.cognitiveservices.speech, jiwer, paho.mqtt.client, webrtcvad
print("Alle packages OK")
EOF

if [ -z "$REBOOT_NODIG" ]; then
    echo -e "\n   i2cdetect -y 1 controle:"
    i2cdetect -y 1 || true
fi

echo -e "\n\033[32m==================================================\033[0m"
echo -e "\033[32mSetup klaar voor device $DEVICE!\033[0m"
if [ -n "$REBOOT_NODIG" ]; then
    echo -e "\033[33mLET OP: reboot nodig voordat I2C werkt -> sudo reboot\033[0m"
fi
echo "Na (eventuele) reboot, controleer:"
echo -e "\033[33m  i2cdetect -y 1\033[0m   # 0x38 (DHT20) en 0x48 (ADS1115) moeten zichtbaar zijn"
echo "Bekende aandachtspunten (zie ook README.md):"
echo "  - GrovePi+ hat is NIET compatibel met deze scripts (directe smbus2/gpiozero i.p.v. hat-driver)"
echo "  - ADS1115 als los I2C-bordje aansluiten, Grove Light op kanaal A0 (niet op GrovePi+ analoge poort)"
echo "  - Grove PIR direct op GPIO17 (pin 11), buiten de GrovePi+ om"
echo "  - ReSpeaker 4 Mic Array via USB aansluiten, test vind_respeaker_device_index() los"
echo "  - Azure Speech vereist nog een API-key (env var, zie speech/azure_speech.py)"
echo "Open een nieuwe shell (of 'source ~/.bashrc') zodat LOODS_DEVICE actief is."
echo -e "Draai daarna de sensor smoke test:\n\033[33m  python3 linux_rpi5/sensor_reader.py\033[0m"
