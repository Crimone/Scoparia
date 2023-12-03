# scp_notify

本地版SCP论坛回复自动提醒系统，该软件完全是运行在本地的，因此推荐使用NAS或托管到云端上，具体这里不做指导。

## 安装

1. clone本仓库
    ```shell
    git clone https://github.com/Crimone/scp_notify.git && cd scp_notify
    ```
2. 配置环境
   ```shell
   pip install -r requirements.txt
   ```
3. 按文件中的注释编辑好 "config.yaml" 文件

## 使用

第一次运行需要先初始化发文记录：

```shell
python scp_notify.py init
```
之后运行
```shell
python scp_notify.py rss
```
即可按配置好的RSS周期自动运行。

本软件完全是运行在本地的——也就是说，程序手动退出或者意外退出之后就会失效。

## Trivia

按本软件的灵感来源的传统，我在这里也肯定的告诉大家：本软件未来有可能会倒闭，也有可能会变质。
