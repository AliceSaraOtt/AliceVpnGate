# AliceVPN 

AliceVPN 是一款智能的 OpenVPN 节点调度与自动代理网关系统。它能自动为您抓取优质免费的节点，内置纯净度与延迟智能优选算法，并将繁琐的 VPN 流量转化为简单易用的本地 HTTP/SOCKS5 代理，同时提供美观的网页版可视化控制台。

## 🚀 Quick Start (快速开始)

在任意一台全新的 Linux 服务器（支持 Ubuntu / Debian / CentOS / Alpine 等主流发行版）上，请使用 `root` 权限执行以下一键部署脚本：

```bash
bash <(curl -sL https://raw.githubusercontent.com/AliceSaraOtt/AliceVpnGate/main/install.sh)
```

### 💡 部署后如何使用？

安装完成后，系统会自动拉起所有服务。您可以在服务器终端直接输入 `al` 呼出管理菜单，或者使用以下快捷命令：

- `al status`：查看服务运行状态、提取本地代理端口以及获取网页后台的登录地址和密码。
- `al restart`：重启 AliceVPN 服务并重新优选节点。
- `al stop`：停止 AliceVPN 服务。
- `al update`：一键自动从 GitHub 拉取最新代码并热更新。

### ✨ 核心特性

*   **极简部署**：一条命令完成系统环境配置、依赖安装及源码部署。
*   **智能节点优选**：内置评分算法，自动识别「住宅 IP」，规避高风险机房 IP。
*   **可视化管理后台**：随时通过浏览器查看当前节点状态、地理位置、真实出口 IP 及延迟。
*   **自动代理转换**：将底层 OpenVPN 隧道直接封装为 `http_proxy` / `socks5_proxy`，极其适合爬虫、自动化脚本或任意 CLI 工具使用。
