#!/usr/bin/env bash
# =============================================================================
#  kk ロボット用 Raspberry Pi セットアップスクリプト  (Ubuntu 24.04 / ROS 2 Jazzy)
# -----------------------------------------------------------------------------
#  対象: Raspberry Pi 5 (aarch64) + Ubuntu 24.04 LTS
#  内容:
#    1. パスワード無し sudo の設定
#    2. 2GB スワップ領域の作成
#    3. ubuntu-desktop / ros-jazzy-desktop と関連ツールの導入
#    4. kk_rescue_pi 各コンポーネントの依存パッケージ導入
#    5. ROS2 ワークスペース kk_ws の作成とリポジトリのクローン
#       (kk_rescue_pi / ros2_socketcan)
#    6. colcon ビルド
#    7. master control の自動起動(systemd)設定
#    8. ~/.bashrc への ROS2 source 追記
#
#  Pi 上で動くプログラムはすべて kk_rescue_pi リポジトリに集約されています:
#    - master_control/     : Web UI つきプログラム起動管理サーバ (port 80)
#    - camera_publisher/   : USB カメラ → WebRTC 配信 (relay へ)
#    - mic_publisher/      : USB マイク → FLAC ロスレス TCP 配信
#    - ros2/joy_node_web/  : Web ゲームパッド → sensor_msgs/Joy (colcon 対象)
#
#  ※ webrtc の中継(SFU=relay)サーバとビューアは「別マシン」で動かします
#    (ClaudeShareContents/webrtc-camera の relay/web を参照)。relay は
#    RELAY_HOST:8080。publisher は relay が落ちても自動再接続します。
#
#  使い方:
#    git clone https://github.com/KinkiKnights/kk_rescue_pi.git
#    ./kk_rescue_pi/setup/kk_robot_setup.sh
#    RELAY_HOST=192.168.137.1 ./kk_rescue_pi/setup/kk_robot_setup.sh  # 中継IP変更時
#
#  ※ 別のラズパイでもそのまま実行できます。PI_ID はホスト名から自動生成します
#    (例: hostname=kk06 → PI_ID=KK06)。
# =============================================================================
set -euo pipefail

# ---- 設定(必要に応じて変更)------------------------------------------------
ROS_DISTRO="jazzy"
WS="$HOME/kk_ws"                                   # ワークスペース
REPO_URL="https://github.com/KinkiKnights/kk_rescue_pi.git"
REPO_DIR="${WS}/src/kk_rescue_pi"
PI_MODEL="pi5"                                     # publish-${PI_MODEL}.sh を使用 (pi4=HW / pi5=SW)
RELAY_HOST="${RELAY_HOST:-192.168.137.1}"          # webrtc 中継(SFU)サーバのIP
RELAY_URL="ws://${RELAY_HOST}:8080/ws"
PI_ID="${PI_ID:-$(hostname | tr '[:lower:]' '[:upper:]')}"   # 配信ID(ホスト名から自動生成)
# カメラ入力ソース (camChange の番号1)。
#   USBカメラ(MJPEG出力)の例: "v4l2src device=/dev/video0 ! image/jpeg,width=1024,height=768,framerate=30/1 ! jpegdec"
#   CSIカメラの場合は         : "libcamerasrc"
CAM1_SRC="${CAM1_SRC:-v4l2src device=/dev/video0 ! image/jpeg,width=1024,height=768,framerate=30/1 ! jpegdec}"
# マイク配信 (mic_publisher / FLAC ロスレス TCP)
MIC_ALSA_DEV="${MIC_ALSA_DEV:-hw:1,0}"   # USBマイク (arecord -l で確認)
MIC_RATE="${MIC_RATE:-48000}"            # 48000 または 44100 (マイクのネイティブ)
MIC_PORT="${MIC_PORT:-5005}"             # 配信TCPポート
USER_NAME="$(id -un)"

log() { printf '\033[1;36m[kk-setup]\033[0m %s\n' "$*"; }

# =============================================================================
# 1. パスワード無し sudo の設定
#    /etc/sudoers.d/ に NOPASSWD 設定を作成。最初の sudo で1度だけパスワードを聞かれます。
# =============================================================================
log "1. パスワード無し sudo を設定"
if ! sudo -n true 2>/dev/null; then
  echo "${USER_NAME} ALL=(ALL) NOPASSWD:ALL" | sudo tee "/etc/sudoers.d/${USER_NAME}-nopasswd" >/dev/null
  sudo chmod 440 "/etc/sudoers.d/${USER_NAME}-nopasswd"
  sudo visudo -c -f "/etc/sudoers.d/${USER_NAME}-nopasswd"   # 文法チェック
fi
log "   -> 以後 sudo はパスワード不要"

# =============================================================================
# 2. 2GB スワップ領域の作成 (/swapfile) と /etc/fstab への永続化
# =============================================================================
log "2. 2GB スワップを作成"
if ! swapon --show | grep -q '/swapfile'; then
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
fi
grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
log "   -> $(swapon --show | grep /swapfile || echo 'swap 有効')"

# =============================================================================
# 3. apt リポジトリ準備 と 大型パッケージの導入
# =============================================================================
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a          # サービス再起動の確認ダイアログを抑制

log "3-1. universe リポジトリと基本ツール"
sudo add-apt-repository -y universe
sudo apt-get update -qq
sudo apt-get install -y curl gnupg lsb-release ca-certificates git

log "3-2. ROS 2 apt リポジトリを追加"
if ! dpkg -s ros2-apt-source >/dev/null 2>&1; then
  RAS_VER=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
            | grep -F '"tag_name"' | awk -F\" '{print $4}')
  CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
  curl -L -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${RAS_VER}/ros2-apt-source_${RAS_VER}.${CODENAME}_all.deb"
  sudo apt-get install -y /tmp/ros2-apt-source.deb
  sudo apt-get update -qq
fi

log "3-3. ROS 2 開発ツール / ros-${ROS_DISTRO}-desktop / ubuntu-desktop を導入(時間がかかります)"
sudo -E apt-get install -y python3-colcon-common-extensions python3-rosdep python3-vcstool ros-dev-tools
sudo -E apt-get install -y "ros-${ROS_DISTRO}-desktop"
sudo -E apt-get install -y ubuntu-desktop

# =============================================================================
# 4. 各コンポーネントの依存パッケージ
# =============================================================================
log "4-1. master_control の依存 (psutil)"
sudo apt-get install -y python3-psutil

log "4-2. joy_node_web の依存 (FastAPI / uvicorn / websockets)"
sudo apt-get install -y python3-fastapi python3-uvicorn python3-websockets

log "4-3. camera_publisher の依存 (GStreamer / Python GI / libcamera)"
sudo apt-get install -y \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-nice gstreamer1.0-libav \
  python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 \
  gir1.2-gst-plugins-base-1.0 gir1.2-gst-plugins-bad-1.0 \
  python3-websockets v4l-utils
# CSIカメラ等の任意パッケージ(無い環境では無視)
sudo apt-get install -y gstreamer1.0-libcamera libcamera-tools gstreamer1.0-plugins-ugly 2>/dev/null \
  || log "   (任意パッケージはスキップ)"

# =============================================================================
# 5. ROS2 ワークスペース kk_ws の作成とリポジトリのクローン
#    Pi 側プログラムは kk_rescue_pi に集約済み。外部依存 (ros2_socketcan) は
#    setup/kk_rescue_pi.repos に定義し vcstool で取得します。
# =============================================================================
log "5. ワークスペース ${WS} を作成しリポジトリをクローン"
mkdir -p "${WS}/src"
cd "${WS}/src"

[ -d "${REPO_DIR}" ] || git clone "${REPO_URL}" "${REPO_DIR}"
vcs import "${WS}/src" < "${REPO_DIR}/setup/kk_rescue_pi.repos"
chmod +x "${REPO_DIR}/camera_publisher/"*.sh "${REPO_DIR}/mic_publisher/"*.sh

# =============================================================================
# 6. rosdep 初期化 と colcon ビルド
#    colcon は package.xml を持つパッケージのみビルド:
#      kk_rescue_pi/ros2/joy_node_web / ros2_socketcan / ros2_socketcan_msgs
#    (master_control / camera_publisher / mic_publisher は ROS パッケージではない)
#    rosdep が ros2_socketcan の依存 (ros-jazzy-can-msgs 等) を自動導入します。
# =============================================================================
log "6. rosdep 解決と colcon ビルド"
sudo rosdep init 2>/dev/null || true
rosdep update
source "/opt/ros/${ROS_DISTRO}/setup.bash"
cd "${WS}"
rosdep install --from-paths src --ignore-src -r -y || log "   (rosdep 一部スキップ)"
colcon build --symlink-install

# =============================================================================
# 7. master control: カメラ/joy_node_web/mic を登録 + 自動起動(systemd)
#    systemd ユニットはこのスクリプトだけが生成します(重複定義を持たない)。
# =============================================================================
log "7-1. programs.json にカメラ / joy_node_web / mic を登録"
cat > "${REPO_DIR}/master_control/programs.json" <<JSON
[
  {"id": 1, "name": "camera",       "type": "bash", "cmd": "PI_ID=${PI_ID} SERVER=${RELAY_URL} CAM1=\"${CAM1_SRC}\" ${REPO_DIR}/camera_publisher/publish-${PI_MODEL}.sh"},
  {"id": 2, "name": "joy_node_web", "type": "ros2", "cmd": "source ${WS}/install/setup.bash && ros2 run joy_node_web joy_node"},
  {"id": 3, "name": "mic",          "type": "bash", "cmd": "ALSA_DEV=${MIC_ALSA_DEV} RATE=${MIC_RATE} PORT=${MIC_PORT} ${REPO_DIR}/mic_publisher/mic-publish.sh"}
]
JSON

log "7-2. master-control.service を作成(kk ユーザで port 80 を bind)"
sudo tee /etc/systemd/system/master-control.service >/dev/null <<UNIT
[Unit]
Description=kk_rescue_pi Master Control
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
Group=${USER_NAME}
AmbientCapabilities=CAP_NET_BIND_SERVICE
Environment=HOME=${HOME}
WorkingDirectory=${REPO_DIR}/master_control
ExecStart=/usr/bin/python3 ${REPO_DIR}/master_control/master_server.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now master-control.service

# =============================================================================
# 8. ~/.bashrc に ROS2 の source を追記
# =============================================================================
log "8. ~/.bashrc に ROS2 source を追記"
if ! grep -q "kk robot setup" "$HOME/.bashrc"; then
  cat >> "$HOME/.bashrc" <<EOF

# ===== ROS 2 (kk robot setup) =====
[ -f /opt/ros/${ROS_DISTRO}/setup.bash ] && source /opt/ros/${ROS_DISTRO}/setup.bash
[ -f "\$HOME/kk_ws/install/setup.bash" ] && source "\$HOME/kk_ws/install/setup.bash"
EOF
fi

# =============================================================================
# 9. 簡易セルフチェック (失敗してもスクリプトは止めない)
# =============================================================================
log "9. セルフチェック"
sleep 2
systemctl is-active --quiet master-control.service && echo "   [OK] master-control 稼働中" || echo "   [NG] master-control 停止"
curl -s -o /dev/null --max-time 5 -w "   [HTTP %{http_code}] master control UI\n" "http://127.0.0.1:80/" || echo "   [NG] UI 応答なし"
source "/opt/ros/${ROS_DISTRO}/setup.bash"; source "${WS}/install/setup.bash" 2>/dev/null || true
ros2 pkg executables joy_node_web 2>/dev/null | grep -q joy_node && echo "   [OK] joy_node_web ビルド済み" || echo "   [NG] joy_node_web 未ビルド"
ls "${REPO_DIR}/camera_publisher/publish-${PI_MODEL}.sh" >/dev/null 2>&1 && echo "   [OK] camera publisher 配置済み" || echo "   [NG] camera publisher なし"
ls "${REPO_DIR}/mic_publisher/mic-publish.sh" >/dev/null 2>&1 && echo "   [OK] mic publisher 配置済み" || echo "   [NG] mic publisher なし"

log "=== セットアップ完了 ==="
echo "  - master control:  http://<このPiのIP>/        (port 80, 自動起動済み)"
echo "  - joy_node_web:    http://<このPiのIP>:8700/joy (master control から起動)"
echo "  - camera:          PI_ID=${PI_ID}  RELAY=${RELAY_URL}"
echo "  - mic:             FLACロスレス配信 tcp://<このPiのIP>:${MIC_PORT} (dev=${MIC_ALSA_DEV})"
echo "  - カメラ/joy/micは master control の Web UI から起動します(自動起動はしません)。"
echo "  - 反映には再ログイン、または 'source ~/.bashrc' を実行してください。"
