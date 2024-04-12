import asyncio
import websockets
import json
import hmac
import base64
import requests
from datetime import datetime, timezone, timedelta
import time

def get_timestamp():
    now = datetime.now()
    t = now.isoformat("T", "milliseconds")
    return t + "Z"


def get_server_time():
    url = "https://www.okx.com/api/v5/public/time"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()['data'][0]['ts']
    else:
        return ""


def get_local_timestamp():
    return int(time.time())


def login_params(timestamp, api_key, passphrase, secret_key):
    message = timestamp + 'GET' + '/users/self/verify'

    mac = hmac.new(bytes(secret_key, encoding='utf8'), bytes(message, encoding='utf-8'), digestmod='sha256')
    d = mac.digest()
    sign = base64.b64encode(d)

    login_param = {"op": "login", "args": [{"apiKey": api_key,
                                            "passphrase": passphrase,
                                            "timestamp": timestamp,
                                            "sign": sign.decode("utf-8")}]}
    login_str = json.dumps(login_param)
    return login_str


async def keep_alive(ws, timeout=30):
    while True:
        try:
            # 如果定时器被触发（N 秒内没有收到新消息），发送 'ping'
            await asyncio.wait_for(ws.recv(), timeout=timeout)
        except asyncio.TimeoutError:
            # 在 N 秒内未收到新消息，发送 'ping'
            await ws.send('ping')
            # 等待 'pong'，如果在 N 秒内未收到，请发出错误或重新连接
            pong = await ws.recv()
            if pong != 'pong':
                raise websockets.exceptions.ConnectionClosed()
            
async def trade_on_open(ws, trade_param, target_time):
    print("Waiting...")
    # 等待到上线前1秒的时刻
    while datetime.now(timezone.utc) < target_time - timedelta(seconds=1):
        await asyncio.sleep(0.01)  # 10ms 的小睡，减少 CPU 使用

    # 当接近上线时间时，每隔334ms发送一次下单请求
    while datetime.now(timezone.utc) < target_time + timedelta(seconds=0.5):
       
        await ws.send(json.dumps(trade_param))
        print(f"Sent order at {datetime.now(timezone.utc).isoformat()}")
        await asyncio.sleep(0.334)

    print("Market is open, the order(s) should have been sent.")

async def main(api_key, passphrase, secret_key, trade_param):
    target_time = datetime(2024, 4, 12, 8, 0, tzinfo=timezone.utc)
    
    url = "wss://ws.okx.com:8443/ws/v5/private"
    while True:
        try:
            async with websockets.connect(url) as ws:
                timestamp = str(get_local_timestamp())
                login_str = login_params(timestamp, api_key, passphrase, secret_key)
                await ws.send(login_str)
                print("Login response:", await ws.recv())
                keep_alive_task = asyncio.create_task(keep_alive(ws, keep_alive_timeout))
                trade_task = asyncio.create_task(trade_on_open(ws, trade_param, target_time))
                done, pending = await asyncio.wait(
                            {keep_alive_task, trade_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                if trade_task in done:
                    keep_alive_task.cancel()
                    break
        except websockets.exceptions.ConnectionClosed:
           print("Connection closed, reconnecting...")
           await asyncio.sleep(1)


trade_param = {
    "id": "1512", 
    "op": "order", 
    "args": [{
        "side": "buy", 
        "instId": "FOXY-USDT", 
        "tdMode": "cash", 
        "ordType": "market", 
        "sz": "300"
    }]
}
keep_alive_timeout = 5
api_key = ""
secret_key = "" 
passphrase = ""
asyncio.run(main(api_key, passphrase, secret_key, trade_param))