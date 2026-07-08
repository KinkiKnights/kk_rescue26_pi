# kk_rescue26_pi

KinkiKnights レスキューロボットの Raspberry Pi 上で動作するプログラム一式。
(旧リポジトリ名: piMasterControl)

- **対象ハード**: Raspberry Pi 5 (aarch64) / **OS**: Ubuntu 24.04 LTS / **ROS**: ROS 2 Jazzy
- 複数台の Pi へ同一手順で展開可能(`PI_ID` はホスト名から自動生成: kk05 → KK05)

## クイックスタート

```bash
cd ~/kk_ws/src   # 無ければ mkdir -p ~/kk_ws/src
git clone https://github.com/KinkiKnights/kk_rescue26_pi.git
./kk_rescue26_pi/setup/kk_robot_setup.sh
```

セットアップ後、`http://<PiのIP>/` の Web UI から camera / joy_node_web / mic を起動できます。

## 構成

Pi 固有のプログラムだけを本リポジトリに置き、汎用/外部の ROS2 パッケージ
(joy_node_web / ros2_socketcan)は `setup/kk_rescue26_pi.repos` で別リポジトリを参照します。

```
kk_rescue26_pi/
├── master_control/      # プログラム起動管理サーバ (port 80, systemd 自動起動)
│   ├── master_server.py #   Web UI から programs.json のプログラムを起動/停止
│   └── programs.json    #   このPi固有の登録内容 (セットアップスクリプトが生成)
├── camera_publisher/    # USB カメラ → WebRTC 配信 (外部 relay へ)
├── mic_publisher/       # USB マイク → FLAC ロスレス TCP 配信 (:5005)
└── setup/
    ├── kk_robot_setup.sh      # Pi 一括セットアップ (systemd ユニットもここで生成)
    └── kk_rescue26_pi.repos   # 外部依存 (joy_node_web / ros2_socketcan) の vcstool 定義

# .repos で ~/kk_ws/src に別途 clone される (colcon ビルド対象):
#   joy_node_web/     Web ゲームパッド → sensor_msgs/Joy (:8700/joy)
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
| joy_node_web | [KinkiKnights/joy_node_web](https://github.com/KinkiKnights/joy_node_web)(他ロボットでも使う汎用パッケージ。取り込まず `.repos` で参照) |
| ros2_socketcan | [autowarefoundation/ros2_socketcan](https://github.com/autowarefoundation/ros2_socketcan)(上流 OSS。取り込まず `.repos` で参照) |
| webrtc relay(SFU)・web ビューア | [ClaudeShareContents/webrtc-camera](https://github.com/sanjofumihiro/ClaudeShareContents)(`publisher/` は本リポジトリへ移設済み) |
| mic receiver | [KinkiKnights/MicStreamRes2026](https://github.com/KinkiKnights/MicStreamRes2026)(`publisher/` は本リポジトリへ移設済み) |

### 二重管理の回避

- **joy_node_web は取り込まない。** 単体で他プロジェクトでも使うため、本リポジトリには
  コピーを置かず `.repos` から clone します。修正は joy_node_web リポジトリ側で行えば
  全プロジェクトに反映されます。
- **ネットワークで結合する相手(relay / receiver)とはプロトコル契約で結合。**
  片側を変更したら、必ず対向リポジトリも同時に更新すること。
  - `camera_publisher` ⇔ relay: WebSocket シグナリング (`ws://<relay>:8080/ws`)
  - `mic_publisher` ⇔ receiver: FLAC over TCP (`:5005`)

  詳細は各ディレクトリの README を参照。

### 外部依存の更新

```bash
vcs pull ~/kk_ws/src          # joy_node_web / ros2_socketcan を上流に追従
cd ~/kk_ws && colcon build
```

## 運用メモ

- master control は systemd (`master-control.service`) で自動起動。ユニットファイルは
  `setup/kk_robot_setup.sh` だけが生成します(リポジトリ内に .service ファイルの複製を置かない)。
- `master_control/programs.json` はセットアップスクリプトが Pi ごとに生成する運用ファイルです。
  リポジトリには KK05 の実例をコミットしてあります。
- サービス操作: `sudo systemctl restart master-control.service` / `journalctl -u master-control -f`
