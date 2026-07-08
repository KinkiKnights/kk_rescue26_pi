import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from sensor_msgs.msg import Joy
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import uvicorn
import threading


app = FastAPI()
msg = Joy()
msg2 = Joy()

HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>JoyNodeWebClient</title>
  <style>
    body { background-color: #353333; color: #eee; font-weight: bold; font-size: 18px; padding: 24px; }
    input[type=text] { background: #222; color: #eee; border: 1px solid #666; padding: 6px 10px; font-size: 16px; margin-right: 8px; }
    button, .btn-file { background: #555; color: #eee; border: 1px solid #888; padding: 6px 16px; cursor: pointer; font-size: 16px; font-weight: bold; margin-right: 8px; }
    button:hover, .btn-file:hover { background: #777; }
    .dot { display: inline-block; width: 14px; height: 14px; border-radius: 50%; background: #888; vertical-align: middle; margin-right: 8px; }
    .dot.connected { background: #4f4; }
    .dot.connecting { background: #fa0; }
    .dot.error { background: #f44; }
    .log { background: #222; border: 1px solid #555; padding: 8px; height: 120px; overflow-y: auto; font-size: 13px; font-weight: normal; margin-top: 12px; line-height: 1.6; }
    .km-info { font-size: 15px; margin-left: 4px; }
    .km-info.none { color: #888; font-weight: normal; }
    .section { margin-bottom: 28px; }
    .axes-grid { display: flex; flex-wrap: wrap; gap: 20px; margin-bottom: 20px; }
    .axis-item { font-size: 16px; min-width: 160px; }
    .axis-bar { height: 6px; background: #555; margin-top: 4px; }
    .axis-fill { height: 100%; background: #aef; width: 50%; }
    .btns-wrap { display: flex; flex-wrap: wrap; gap: 10px; }
    .bb { min-width: 44px; padding: 6px 8px; background: #444; border: 1px solid #666; text-align: center; font-size: 14px; color: #aaa; }
    .bb.pressed { background: #eee; color: #333; border-color: #eee; }
    #gp-name { margin-bottom: 16px; }
  </style>
</head>
<body>
  <div class="section">
    <span class="dot" id="dot"></span>
    <input type="text" id="ws-url" placeholder="ws://hostname/joys" size="36">
    <button onclick="doConnect()">Connect</button>
    <button onclick="doDisconnect()">Disconnect</button>
    <div class="log" id="log"></div>
  </div>

  <div class="section">
    <label class="btn-file">ファイルからキーマップを読み込み<input type="file" id="km-file" accept=".json" style="display:none" onchange="loadKeymap(event)"></label>
    <button onclick="clearKeymap()">キーマップクリア</button>
    <span class="km-info none" id="km-info">キーマップなし (生データ)</span>
  </div>

  <div id="gp-name">Gamepad: not connected</div>
  <div class="axes-grid"  id="axes-grid"></div>
  <div class="btns-wrap"  id="btns-grid"></div>

<script>
// ── Standard gamepad layout (W3C) ────────────────────────────────────────
const STD_BUTTONS = [
  'face_down','face_right','face_left','face_up',
  'shoulder_l','shoulder_r','trigger_l','trigger_r',
  'select','start','stick_l_click','stick_r_click',
  'dpad_up','dpad_down','dpad_left','dpad_right','home'
];
const STD_AXES = ['stick_l_x','stick_l_y','stick_r_x','stick_r_y'];

// button groups (index into STD_BUTTONS): ABXY / LBRBLTRT / SELECT…HOME / dpad
const BTN_GROUPS = [
  [0,1,2,3],
  [4,5,6,7],
  [8,9,10,11,16],
  [12,13,14,15],
];

// friendly short labels for display
const BTN_LABEL = {
  face_down:'▼ A', face_right:'▶ B', face_left:'◀ X', face_up:'▲ Y',
  shoulder_l:'LB', shoulder_r:'RB', trigger_l:'LT', trigger_r:'RT',
  select:'Select', start:'Start', stick_l_click:'LS', stick_r_click:'RS',
  dpad_up:'↑', dpad_down:'↓', dpad_left:'←', dpad_right:'→', home:'Home'
};
const AXIS_LABEL = {
  stick_l_x:'LX', stick_l_y:'LY', stick_r_x:'RX', stick_r_y:'RY'
};

// ── State ─────────────────────────────────────────────────────────────────
const status   = { pad_index:0, pad_connect:false, ws:null, trying:false };
const pad_info = { id:'unknown', buttons:[], axes:[] };
let   keymap   = null;   // null = raw passthrough

// ── Logging ───────────────────────────────────────────────────────────────
function log(msg, cls) {
  const el  = document.getElementById('log');
  const now = new Date().toTimeString().slice(0,8);
  el.innerHTML += '<div><span class="ts">'+now+'</span>'
                + '<span class="'+(cls||'')+'">'+msg+'</span></div>';
  el.scrollTop = el.scrollHeight;
}
function setDot(s){ document.getElementById('dot').className='dot '+s; }

// ── WebSocket ─────────────────────────────────────────────────────────────
const uri_obj    = new URL(window.location.href);
const defaultUrl = 'ws://' + uri_obj.host + '/joys';
document.getElementById('ws-url').value = defaultUrl;

function doConnect() {
  if (status.ws && status.ws.readyState === WebSocket.OPEN){ log('Already connected','inf'); return; }
  const url = document.getElementById('ws-url').value.trim();
  if (!url) return;
  wsInit(url);
}
function doDisconnect() {
  if (status.ws){ status.ws.onclose=null; status.ws.close(); status.ws=null; }
  status.trying=false; setDot('error'); log('Disconnected by user','err');
}
function wsInit(url) {
  if (status.trying) return;
  status.trying=true; setDot('connecting'); log('Connecting '+url+' …','inf');
  const ws = new WebSocket(url);
  ws.onopen  = ()=>{ status.ws=ws; status.trying=false; setDot('connected'); log('Connected: '+url,'ok'); };
  ws.onclose = ()=>{ status.ws=null; status.trying=false; setDot('error'); log('Closed','err'); };
  ws.onerror = ()=>{ log('WebSocket error','err'); };
  ws.onmessage = (e)=>{
    try{ const d=JSON.parse(e.data); if(d.source==='can') updateDisplay(d.axes,d.buttons,true); }catch(_){}
  };
}
function retryWebsocket() {
  if (status.ws && status.ws.readyState===WebSocket.OPEN) return;
  if (status.trying) return;
  const url = document.getElementById('ws-url').value.trim();
  if (!url) return;
  log('Retrying …','inf'); wsInit(url);
}

// ── Keymap ────────────────────────────────────────────────────────────────
function applyKeymapData(data) {
  keymap = data.mapping;
  const infoEl = document.getElementById('km-info');
  infoEl.textContent = (data.gamepadId || 'Unknown') + (data.version ? '  v'+data.version : '');
  infoEl.className = 'km-info';
}

function loadKeymap(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);
      if (!data.mapping) throw new Error('mapping field missing');
      applyKeymapData(data);
      localStorage.setItem('joy_keymap', e.target.result);
      log('キーマップ読み込み: ' + (data.gamepadId || 'Unknown'), 'ok');
    } catch(err) {
      log('キーマップ読み込み失敗: ' + err.message, 'err');
    }
    event.target.value = '';
  };
  reader.readAsText(file);
}

function clearKeymap() {
  keymap = null;
  localStorage.removeItem('joy_keymap');
  const el = document.getElementById('km-info');
  el.textContent = 'キーマップなし (生データ)';
  el.className = 'km-info none';
  log('キーマップクリア', 'inf');
  rebuildDisplay([], []);
}

// ── Mapping logic ─────────────────────────────────────────────────────────
function applyMapping(rawAxes, rawButtons) {
  if (!keymap) return { axes: Array.from(rawAxes), buttons: rawButtons.map(b=>b) };

  const buttons = STD_BUTTONS.map(name => {
    const m = keymap[name];
    if (!m) return 0;
    if (m.kind === 'button') return rawButtons[m.index] || 0;
    if (m.kind === 'axis') {
      const v = rawAxes[m.index] || 0;
      return (v + 1) / 2;           // axis -1..1 → button 0..1
    }
    return 0;
  });

  const axes = STD_AXES.map(name => {
    const m = keymap[name];
    if (!m) return 0;
    if (m.kind === 'axis')   return rawAxes[m.index] || 0;
    if (m.kind === 'button') return rawButtons[m.index] ? 1.0 : 0.0;
    return 0;
  });

  return { axes, buttons };
}

// ── Gamepad polling ───────────────────────────────────────────────────────
window.addEventListener('gamepadconnected', (e) => {
  pad_info.id = e.gamepad.id;
  status.pad_index = e.gamepad.index;
  status.pad_connect = true;
  document.getElementById('gp-name').textContent = 'Gamepad: ' + pad_info.id;
  log('Gamepad connected: ' + pad_info.id, 'ok');
});
window.addEventListener('gamepaddisconnected', (e) => {
  if (e.gamepad.index === status.pad_index) {
    status.pad_connect = false;
    document.getElementById('gp-name').textContent = 'Gamepad: disconnected';
    log('Gamepad disconnected', 'err');
    rebuildDisplay([], []);
  }
});

function updateGamepad() {
  if (!status.pad_connect) return;
  const gp = navigator.getGamepads()[status.pad_index];
  if (!gp) return;

  const rawAxes    = Array.from(gp.axes);
  const rawButtons = gp.buttons.map(b => b.value);

  const { axes, buttons } = applyMapping(rawAxes, rawButtons);

  pad_info.axes    = axes;
  pad_info.buttons = buttons;

  updateDisplay(axes, buttons, false);

  if (status.ws && status.ws.readyState === WebSocket.OPEN) {
    status.ws.send(JSON.stringify(pad_info));
  }
}

// ── Display ───────────────────────────────────────────────────────────────
let _axisCount = -1, _btnCount = -1;

function axisLabel(i) {
  if (keymap && i < STD_AXES.length) return AXIS_LABEL[STD_AXES[i]] || STD_AXES[i];
  return 'axis[' + i + ']';
}
function btnLabel(i) {
  if (keymap && i < STD_BUTTONS.length) return BTN_LABEL[STD_BUTTONS[i]] || STD_BUTTONS[i];
  return '' + i;
}

function rebuildDisplay(axes, buttons) {
  _axisCount = axes.length;
  _btnCount  = buttons.length;

  const ag = document.getElementById('axes-grid');
  ag.innerHTML = axes.map(function(_,i){
    return '<div class="axis-item">'
      + '<span class="axis-lbl">'+axisLabel(i)+'</span>'
      + '<span class="axis-val" id="av'+i+'">0.000</span>'
      + '<div class="axis-bar"><div class="axis-fill" id="ab'+i+'"></div></div>'
      + '</div>';
  }).join('');

  const bg = document.getElementById('btns-grid');
  if (keymap && buttons.length > 12) {
    const BR = '<div style="flex-basis:100%;height:6px"></div>';
    bg.innerHTML = BTN_GROUPS.map(function(group){
      return group.filter(function(i){ return i < buttons.length; })
                  .map(function(i){ return '<div class="bb" id="bb'+i+'">'+btnLabel(i)+'</div>'; })
                  .join('');
    }).join(BR);
  } else {
    bg.innerHTML = buttons.map(function(_,i){
      return '<div class="bb" id="bb'+i+'">'+btnLabel(i)+'</div>';
    }).join('');
  }
}

function updateDisplay(axes, buttons, fromCan) {
  if (axes.length !== _axisCount || buttons.length !== _btnCount) {
    rebuildDisplay(axes, buttons);
  }
  axes.forEach(function(v,i){
    var el=document.getElementById('av'+i), br=document.getElementById('ab'+i);
    if(el) el.textContent = parseFloat(v).toFixed(3);
    if(br) br.style.width = ((parseFloat(v)+1)*50)+'%';
  });
  buttons.forEach(function(v,i){
    var el=document.getElementById('bb'+i);
    if(el) el.className='bb'+(v?' pressed':'');
  });
}

// ── localStorage 復元 ─────────────────────────────────────────────────────
(function() {
  const saved = localStorage.getItem('joy_keymap');
  if (saved) {
    try {
      const data = JSON.parse(saved);
      if (data.mapping) {
        applyKeymapData(data);
        log('キーマップ復元: ' + (data.gamepadId || 'Unknown'), 'ok');
      }
    } catch(_) { localStorage.removeItem('joy_keymap'); }
  }
})();

setInterval(updateGamepad,   50);
setInterval(retryWebsocket, 5000);
wsInit(defaultUrl);
</script>
</body>
</html>"""


@app.get("/joy")
async def get():
    return HTMLResponse(HTML)


@app.websocket("/joys")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    global msg, msg2
    while True:
        gamepad_info = await websocket.receive_json()
        if "type" in gamepad_info and gamepad_info["type"] == 1:
            msg_in = msg2
        else:
            msg_in = msg

        for i in range(len(gamepad_info["axes"])):
            if len(msg_in.axes) <= i:
                msg_in.axes.append(gamepad_info["axes"][i])
            else:
                msg_in.axes[i] = gamepad_info["axes"][i]

        for i in range(len(gamepad_info["buttons"])):
            if len(msg_in.buttons) <= i:
                msg_in.buttons.append(int(gamepad_info["buttons"][i]))
            else:
                msg_in.buttons[i] = int(gamepad_info["buttons"][i])


def web_start():
    print("boot webserver thread")
    uvicorn.run(app, host="0.0.0.0", port=8700)


def exchangeMapping(mapping):
    # comming soon
    return mapping


class JoyNodeWeb(Node):
    def __init__(self):
        super().__init__("joy_node_web")
        qos_profile = QoSProfile(depth=2)
        self.timer = self.create_timer(0.05, self.update_joy)
        self.pub  = self.create_publisher(Joy, "/joy",  qos_profile=qos_profile)
        self.pub2 = self.create_publisher(Joy, "/joy2", qos_profile=qos_profile)

    def update_joy(self):
        global msg, msg2
        msg.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)
        self.pub2.publish(msg2)


def main(args=None):
    rclpy.init(args=args)
    thread_web = threading.Thread(target=web_start)
    thread_web.start()
    joy_node = JoyNodeWeb()
    print("please open domain:8700/joy")
    rclpy.spin(joy_node)


if __name__ == '__main__':
    main()
