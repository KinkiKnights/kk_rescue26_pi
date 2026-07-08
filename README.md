# kk_rescue26_pi

KinkiKnights レスキューロボットの Raspberry Pi 上で動作するプログラム一式。
(旧リポジトリ名: piMasterControl)

- **対象ハード**: Raspberry Pi 5 (aarch64) / **OS**: Ubuntu 24.04 LTS / **ROS**: ROS 2 Jazzy
- 複数台の Pi へ同一手順で展開可能(`PI_ID` はホスト名から自動生成: kk05 → KK05)

## クイックスタート

新しい Pi では次のワンライナーを貼り付けて実行します。**GitHub にアクセスする前に
SSH キーを生成・表示して登録を待つ**自己完結ブートストラップなので、リポジトリが
非公開でもこの1コマンドで完了します(キー登録 → SSH で clone → 依存導入・ビルド・
自動起動設定まで全自動)。

```bash
bash -c 'set -e; install -d -m700 ~/.ssh; k=$HOME/.ssh/id_ed25519; [ -f "$k" ] || ssh-keygen -t ed25519 -C "$(hostname)-github" -N "" -f "$k" -q; echo "===== この公開鍵を GitHub に登録してください ====="; echo "  アカウント: https://github.com/settings/keys / リポジトリ単位: Settings -> Deploy keys"; cat "$k.pub"; echo "=================================================="; read -rp "登録が完了したら Enter: " < /dev/tty; export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new"; mkdir -p ~/kk_ws/src; [ -d ~/kk_ws/src/kk_rescue26_pi ] || git clone --recursive git@github.com:KinkiKnights/kk_rescue26_pi.git ~/kk_ws/src/kk_rescue26_pi; ~/kk_ws/src/kk_rescue26_pi/setup/kk_robot_setup.sh'
```

中継サーバ(relay)IP やカメラソースを変える場合は、環境変数を先頭に付けます
(セットアップ本体まで引き継がれます):

```bash
RELAY_HOST=192.168.137.1 bash -c '...(上と同じ)...'
# CSI カメラの例: CAM1_SRC=libcamerasrc bash -c '...'
```

キー登録後は、セットアップ本体の冒頭でも SSH 認証を再確認します(認証済みなら
そのまま進行)。最初の `sudo` で1度だけパスワードを聞かれます(以後は NOPASSWD 設定)。
`PI_ID` はホスト名から自動生成されます(例: `kk06` → `KK06`)。
USB WiFi ドングル(RTL8811AU)のドライバも自動導入されます
(接続設定は [docs/usb-wifi-dongle.md](docs/usb-wifi-dongle.md) 参照)。

<details><summary>手動で clone して実行する場合 / 公開リポジトリの場合</summary>

SSH キー登録後に手動で:

```bash
mkdir -p ~/kk_ws/src && cd ~/kk_ws/src
git clone --recursive git@github.com:KinkiKnights/kk_rescue26_pi.git   # submodule も取得
./kk_rescue26_pi/setup/kk_robot_setup.sh
```

`--recursive` を付け忘れた場合は `git -C kk_rescue26_pi submodule update --init` で
joy_node_web(submodule)を取得してください(セットアップスクリプトは自動で init します)。

リポジトリが**公開**の間は、raw URL 経由でも実行できます(スクリプト冒頭でキー登録待ちが走ります):

```bash
curl -fsSL https://raw.githubusercontent.com/KinkiKnights/kk_rescue26_pi/main/setup/kk_robot_setup.sh | bash
```
</details>

セットアップ後、`http://<PiのIP>/` の Web UI から camera / joy_node_web / mic を起動できます。

## 構成

Pi 上で動くプログラムを本リポジトリに集約します。joy_node_web は他ロボットでも
使う共有パッケージのため **submodule**(固定コミットへの参照)として含みます。
外部 OSS の ros2_socketcan のみ `setup/kk_rescue26_pi.repos` で参照します。

```
kk_rescue26_pi/
├── master_control/      # プログラム起動管理サーバ (port 80, systemd 自動起動)
│   ├── master_server.py #   Web UI から programs.json のプログラムを起動/停止
│   └── programs.json    #   このPi固有の登録内容 (セットアップスクリプトが生成)
├── camera_publisher/    # USB カメラ → WebRTC 配信 (外部 relay へ)
├── mic_publisher/       # USB マイク → FLAC ロスレス TCP 配信 (:5005)
├── ros2/
│   └── joy_node_web/    # [submodule] Web ゲームパッド → sensor_msgs/Joy (colcon 対象, :8700/joy)
└── setup/
    ├── kk_robot_setup.sh      # Pi 一括セットアップ (systemd ユニットもここで生成)
    └── kk_rescue26_pi.repos   # 外部依存 (ros2_socketcan) の vcstool 定義

# .repos で ~/kk_ws/src に別途 clone される (colcon ビルド対象):
#   ros2_socketcan/   CAN 通信
```

### システム全体像

```
[Raspberry Pi]                                 [他デバイス]
  master_control (:80) ──起動/停止──┐
  camera_publisher ──WebRTC──────────→ relay SFU (:8080) → web ビューア
  mic_publisher (:5005) ──FLAC/TCP──→ mic_receiver
  joy_node_web (:8700) ← ブラウザ操作 → /joy → ros2_socketcan → CAN
```

## 他リポジトリとの関係(メンテナンス方針)

**原則: 各コンポーネントの実体はただ1つのリポジトリにのみ置く。**
コピーを複数リポジトリに持たない。これが乖離防止の基本ルールです。

| コンポーネント | 正式な置き場所 (single source of truth) |
|---|---|
| master_control / camera_publisher / mic_publisher | **このリポジトリ** |
| joy_node_web | [KinkiKnights/joy_node_web](https://github.com/KinkiKnights/joy_node_web)(共有パッケージ。本リポジトリには **submodule** として固定コミットで参照) |
| ros2_socketcan | [autowarefoundation/ros2_socketcan](https://github.com/autowarefoundation/ros2_socketcan)(上流 OSS。取り込まず `.repos` で参照) |
| webrtc relay(SFU)・web ビューア | [ClaudeShareContents/webrtc-camera](https://github.com/sanjofumihiro/ClaudeShareContents)(`publisher/` は本リポジトリへ移設済み) |
| mic receiver | [KinkiKnights/MicStreamRes2026](https://github.com/KinkiKnights/MicStreamRes2026)(`publisher/` は本リポジトリへ移設済み) |

### joy_node_web(submodule)の運用

joy_node_web は他ロボットでも使う共有パッケージのため、単一の真実は
[KinkiKnights/joy_node_web](https://github.com/KinkiKnights/joy_node_web) に置き、本リポジトリは
`ros2/joy_node_web` に **submodule(固定コミットへの参照)** として含みます。コードは複製されず、
どの版を積んでいるかは submodule のコミット SHA で明示されます(フリートでの版管理が明確)。

```bash
# 取得(clone 時に付け忘れた場合)
git submodule update --init ros2/joy_node_web

# 上流 (joy_node_web) の最新を取り込み、親リポジトリのポインタを更新
git submodule update --remote ros2/joy_node_web
git add ros2/joy_node_web && git commit -m "Bump joy_node_web submodule"

# joy_node_web 自体を修正する場合は submodule 内で作業してから push し、
# 親リポジトリでポインタ更新をコミットする
cd ros2/joy_node_web && git checkout main && git pull
#   … 編集 … → git commit → git push
cd ../.. && git add ros2/joy_node_web && git commit -m "Bump joy_node_web submodule"
```

### プロトコル契約(乖離防止)

ネットワークで結合する相手(relay / receiver)とはプロトコル契約で結合しています。
**片側を変更したら、必ず対向リポジトリも同時に更新すること。**

- `camera_publisher` ⇔ relay: WebSocket シグナリング (`ws://<relay>:8080/ws`)
- `mic_publisher` ⇔ receiver: FLAC over TCP (`:5005`)

詳細は各ディレクトリの README を参照。

### 外部依存の更新

```bash
vcs pull ~/kk_ws/src          # ros2_socketcan を上流に追従
cd ~/kk_ws && colcon build
```

## 運用メモ

- master control は systemd (`master-control.service`) で自動起動。ユニットファイルは
  `setup/kk_robot_setup.sh` だけが生成します(リポジトリ内に .service ファイルの複製を置かない)。
- `master_control/programs.json` はセットアップスクリプトが Pi ごとに生成する運用ファイルです。
  リポジトリには KK05 の実例をコミットしてあります。
- サービス操作: `sudo systemctl restart master-control.service` / `journalctl -u master-control -f`
