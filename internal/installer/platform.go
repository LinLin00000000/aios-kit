package installer

import "runtime"

const (
	PlatformAuto    = "auto"
	PlatformLinux   = "linux"
	PlatformWindows = "windows"
	PlatformDarwin  = "darwin"
	PlatformUnknown = "unknown"
)

type Capability struct {
	ID          string `json:"id"`
	Title       string `json:"title"`
	Layer       string `json:"layer"`
	Description string `json:"description"`
	Supported   bool   `json:"supported"`
}

func CurrentPlatform() string {
	switch runtime.GOOS {
	case "linux":
		return PlatformLinux
	case "windows":
		return PlatformWindows
	case "darwin":
		return PlatformDarwin
	default:
		return PlatformUnknown
	}
}

func NormalizePlatform(value string) string {
	switch value {
	case "", PlatformAuto:
		return CurrentPlatform()
	case PlatformLinux, PlatformWindows, PlatformDarwin:
		return value
	default:
		return PlatformUnknown
	}
}

func PlatformDefaults(platform string) Options {
	opts := DefaultOptions()
	switch NormalizePlatform(platform) {
	case PlatformWindows:
		opts.Proxy = ChoiceNo
		opts.ProxyTun = false
		opts.ResetSources = false
		opts.WithDevEnv = false
		opts.WithHermes = false
		opts.WithAIOps = false
		// Windows native install.ps1 owns execution. The Go wizard can still print
		// a conservative Bash/WSL command when explicitly used on Windows.
	case PlatformDarwin:
		opts.Proxy = ChoiceNo
		opts.ProxyTun = false
		opts.ResetSources = false
		opts.WithDevEnv = false
	}
	return opts
}

func CapabilitiesForPlatform(platform string) []Capability {
	p := NormalizePlatform(platform)
	linux := p == PlatformLinux
	windows := p == PlatformWindows
	return []Capability{
		{ID: "core-instance", Title: "AIOS Core 本地实例", Layer: "core", Description: "~/aios 目录、config/vault/work/skills/modules/state/logs/cache。", Supported: linux || windows},
		{ID: "core-modules", Title: "aios-kit + LLL 模块", Layer: "core", Description: "安装/更新 aios-kit 与 Lin's Living Loop，支持本地开机即用。", Supported: linux || windows},
		{ID: "core-shims", Title: "aios/lll 命令入口", Layer: "core", Description: "在 AIOS bin 目录暴露命令，并可加入 PATH。", Supported: linux || windows},
		{ID: "skillpack-target", Title: "runtime skills 目标目录", Layer: "core", Description: "初始化 agent runtime skills 目标；Windows managed skillpack sync 暂需 Linux/WSL。", Supported: linux || windows},
		{ID: "dev-env", Title: "开发/运行环境 bootstrap", Layer: "addon", Description: "Python/UV、Node、Docker、Caddy 等。", Supported: linux},
		{ID: "hermes", Title: "Hermes Agent 安装/配置", Layer: "addon", Description: "将 Hermes 作为默认中心 Agent。", Supported: linux},
		{ID: "aiops", Title: "OPS vault 模板", Layer: "addon", Description: "初始化运维资料库模板。", Supported: linux},
		{ID: "proxy", Title: "Mihomo/代理/TUN", Layer: "addon", Description: "Linux/server 网络引导，可选 TUN 和代理环境。", Supported: linux},
		{ID: "reset-sources", Title: "系统软件源恢复", Layer: "addon", Description: "Ubuntu apt、npm、pip、Docker 源恢复。", Supported: linux},
		{ID: "service-24x7", Title: "24/7 服务化运行", Layer: "addon", Description: "systemd 等持续运行能力；本地开机使用不需要。", Supported: linux},
	}
}

func SupportsAddon(platform string, id string) bool {
	for _, cap := range CapabilitiesForPlatform(platform) {
		if cap.ID == id {
			return cap.Supported
		}
	}
	return false
}
