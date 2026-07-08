# JoyNodeWeb
Webブラウザ上でゲームコントローラの操作をキャプチャし、`sensor_msgs::msg::Joy`としてPublishします。

ROS2 Humbleでのみ動作確認を行っています。

# 依存関係のインストール
```bash
sudo apt install python3-pip python3-fastapi python3-uvicorn
```

# リポジトリのビルド
```bash
# ros2の任意のワークスペース内にこのリポジトリをクローンしてビルドします。
git clone https://github.com/KinkiKnights/joy_node_web.git
cd ..
colcon build

# ビルド後にワークスペースを再読み込み
source ./install/local_setup.bash
```

# 起動
```
ros2 run joy_node_web joy_node
```
ノードの起動後、[http://ドメイン or IP:8700/joy](http://127.0.0.1:8700/joy)へアクセスするとコントローラの情報が`/joy`でPublishされます
コントローラのWebクライアントはCROSに違反しない範囲で自由に作成できます。# camera_joy
