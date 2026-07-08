# kk_rescue_pi

KinkiKnights レスキューロボットの Raspberry Pi 上で動作するプログラム一式。
(旧リポジトリ名: piMasterControl)

- **対象ハード**: Raspberry Pi 5 (aarch64) / **OS**: Ubuntu 24.04 LTS / **ROS**: ROS 2 Jazzy
- 複数台の Pi へ同一手順で展開可能(`PI_ID` はホスト名から自動生成: kk05 → KK05)

## クイックスタート

```bash
cd ~/kk_ws/src   # 無ければ mkdir -p ~/kk_ws/src
git clone https://github.com/KinkiKnights/kk_rescue_pi.git
./kk_rescue_pi/setup/kk_robot_setup.sh
```

セットアップ後、`http://<PiのIP>/` の Web UI から camera / joy_node_web / mic を起動できます。

## 構成

```
kk_rescue_pi/
├── master_control/      # プログラム起動管理サーバ (port 80, systemd 自動起動)
│   ├── master_server.py #   Web UI から programs.json のプログラムを起動/停止
│   └── programs.json    #   このPi固有の登録内容 (セットアップスクリプトが生成)
├── camera_publisher/    # USB カメラ → WebRTC 配信 (外部 relay へ)
├── mic_publisher/       # USB マイク → FLAC ロスレス TCP 配信 (:5005)
├── ros2/
│   └── joy_node_web/    # Web ゲームパッド → sensor_msgs/Joy (colcon ビルド対象, :8700/joy)
└── setup/
    ├── kk_robot_setup.sh    # Pi 一括セットアップ (systemd ユニットもここで生成)
    └── kk_rescue_pi.repos   # 外部依存 (ros2_socketcan) の vcstool 定義
```

### システム全体像

```
[Raspberry Pi (このリポジトリ)]                [他デバイス]
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
| master_control / camera_publisher / mic_publisher / joy_node_web | **このリポジトリ** |
| webrtc relay(SFU)・web ビューア | [ClaudeShareContents/webrtc-camera](https://github.com/sanjofumihiro/ClaudeShareContents)(`publisher/` は本リポジトリへ移設済み) |
| mic receiver | [KinkiKnights/MicStreamRes2026](https://github.com/KinkiKnights/MicStreamRes2026)(`publisher/` は本リポジトリへ移設済み) |
| ros2_socketcan | [autowarefoundation/ros2_socketcan](https://github.com/autowarefoundation/ros2_socketcan)(取り込まず `.repos` で参照) |

### プロトコル契約

Pi 側(本リポジトリ)と他デバイス側はネットワークプロトコルで結合しています。
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
