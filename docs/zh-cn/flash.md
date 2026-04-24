# Bridge 出厂烧录指南

## 你拿到的发布包

现在对外发布的 bridge 固件以同一版本目录下的两个 zip 文件交付：

- `./firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/factory.zip`
- `./firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/ota.zip`

本文只使用 `factory.zip` 完成空片或被擦除板卡的首次烧录。`ota.zip` 是后续 ESP OTA 更新用的配套包，详见 [Bridge 设备 OTA 指南](./ota.md)。

## 前置条件

- 以下命令假设当前工作目录为 `mmwk` 项目根目录，也就是同时包含 `firmwares/` 和 `mmwk_cli/` 的那个目录。
- 你已经拿到了目标板卡和版本对应的 bridge 发布 zip 包。
- 选择一种烧录路径：
  - 如果走本地串口擦除加 `factory/flash.sh`，则需要本地已安装 ESP-IDF，且设备串口可用，记为 `<port>`。
  - 如果走 Espressif 官方 `ESP Launchpad` 的 `DIY` 路径，则不需要本地安装 ESP-IDF。

## 先解压 `factory.zip`

请直接使用发布好的 `factory.zip`，先解压到一个临时目录，再执行烧录：

```bash
rm -rf /tmp/mmwk_bridge_factory
mkdir -p /tmp/mmwk_bridge_factory
unzip ./firmwares/esp/<board>/mmwk_sensor_bridge/v<version>/factory.zip -d /tmp/mmwk_bridge_factory
```

解压后你会用到的是：

```text
/tmp/mmwk_bridge_factory/factory/flash.sh
/tmp/mmwk_bridge_factory/factory/mmwk_sensor_bridge_factory_v<version>.bin
```

## 方式 A：本地串口擦除 + 解压后的 `factory/flash.sh`

执行本地擦除和烧录前先加载 ESP-IDF 环境。在这个仓库里，使用你本机实际安装的那一路 export 即可：

```bash
source ~/esp/esp-idf/export.sh
# 或
source ~/esp/esp-adf/esp-idf/export.sh
```

擦除步骤应使用一个临时 build 目录执行 `idf.py`，这样命令可以直接复制执行，而不依赖额外 checkout 的 ESP-IDF 工程目录：

```bash
idf.py -B /tmp/mmwk_idf_erase -p <port> erase-flash
```

然后使用解压出来的出厂包执行烧录：

```bash
cd /tmp/mmwk_bridge_factory/factory
./flash.sh <port>
```

## 方式 B：Espressif 官方 ESP Launchpad DIY

如果要走 Espressif 官方 [`ESP Launchpad`](https://espressif.github.io/esp-launchpad/) 的单文件路径，选择 `DIY`，上传解压后的合并出厂镜像，并把烧录地址填写为 `0x0`。

使用这个解压后的文件：

```text
/tmp/mmwk_bridge_factory/factory/mmwk_sensor_bridge_factory_v<version>.bin
```

## 验证恢复结果

在 `mmwk` 项目根目录下执行：

```bash
./mmwk_cli/mmwk_cli.sh device hi --reset -p <port>
```

`device hi` 应返回 bridge 身份信息。请确认 `device hi.version` 与发布包路径或解压后文件名里携带的版本一致，例如：

```text
./firmwares/esp/mini/mmwk_sensor_bridge/v1.2.2/factory.zip
/tmp/mmwk_bridge_factory/factory/mmwk_sensor_bridge_factory_v1.2.2.bin
```

## 不在本文范围

以下内容不在本文范围：

- 首次烧录后的 ESP OTA 更新流程
- 这两个 zip 包的构建或发布步骤
