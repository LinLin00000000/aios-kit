package wizard

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/huh"

	"github.com/LinLin00000000/aios-kit/internal/installer"
)

func Run(opts installer.Options) (installer.Options, bool, error) {
	return RunForPlatform(opts, installer.CurrentPlatform())
}

func RunForPlatform(opts installer.Options, platform string) (installer.Options, bool, error) {
	platform = installer.NormalizePlatform(platform)
	addPath := opts.AddToPath != installer.ChoiceNo
	useTun := opts.ProxyTun
	resetSources := opts.ResetSources
	dryRun := opts.DryRun
	execute := false
	components := selectedComponents(opts)

	groups := []*huh.Group{
		huh.NewGroup(
			huh.NewNote().
				Title("AIOS 能力分层").
				Description(capabilityDescription(platform)),
			huh.NewInput().
				Title("AIOS 安装根目录").
				Description("核心特性：本地 AIOS 实例根目录。默认 ~/aios；支持 ~，真实展开由安装后端处理。").
				Value(&opts.Root),
			huh.NewConfirm().
				Title("把 AIOS bin 加入 PATH？").
				Description("核心特性：让本地开机使用时可以直接运行 aios/lll。").
				Affirmative("加入").
				Negative("不加入").
				Value(&addPath),
		),
	}

	if platform == installer.PlatformLinux {
		groups = append(groups, huh.NewGroup(
			huh.NewSelect[string]().
				Title("附加能力：代理 / 网络模式").
				Description("Linux/server 可选能力。auto 会先测试直连，失败时再安装 Mihomo。").
				Options(
					huh.NewOption("auto：自动检测（推荐）", installer.ChoiceAuto),
					huh.NewOption("yes：强制安装/配置代理", installer.ChoiceYes),
					huh.NewOption("no：不配置代理", installer.ChoiceNo),
				).
				Value(&opts.Proxy),
			huh.NewConfirm().
				Title("附加能力：开启 Mihomo TUN？").
				Description("Linux 服务器默认推荐开启；本地核心使用并不依赖。私有订阅可安装后再配置。").
				Affirmative("开启").
				Negative("关闭").
				Value(&useTun),
			huh.NewConfirm().
				Title("附加能力：恢复 apt/npm/pip/Docker 官方源？").
				Description("主要面向 Ubuntu/Debian 新服务器。Windows 原生安装不会显示此项。").
				Affirmative("恢复").
				Negative("不修改").
				Value(&resetSources),
			huh.NewInput().
				Title("GitHub/raw 镜像前缀（可空）").
				Description("例如 https://gh-proxy.com/；留空表示直连。").
				Value(&opts.GitHubMirror),
			huh.NewInput().
				Title("代理订阅 URL（可空，私密）").
				Description("不会在摘要中明文显示；也可安装后再配置。").
				Value(&opts.ProxySubscriptionURL),
			huh.NewInput().
				Title("provider id").
				Description("写入 MIHOMO_PROVIDERS_ORDER；默认 main。只用小写字母、数字、下划线。").
				Value(&opts.ProxyProviderID),
		))
	} else {
		// Hide Linux/server-only network and source-reset controls on Windows.
		opts.Proxy = installer.ChoiceNo
		opts.ProxyTun = false
		opts.ResetSources = false
		groups = append(groups, huh.NewGroup(
			huh.NewInput().
				Title("GitHub/raw 镜像前缀（可空）").
				Description("核心安装可选项；例如 https://gh-proxy.com/；留空表示直连。").
				Value(&opts.GitHubMirror),
		))
	}

	if platform == installer.PlatformLinux {
		groups = append(groups, huh.NewGroup(
			huh.NewMultiSelect[string]().
				Title("选择附加能力").
				Description("核心能力总会安装；这些是 Linux/server 推荐但非必需的扩展能力。空格复选，上下键移动，回车确认。").
				Options(
					huh.NewOption("开发/运行环境：Python/UV、Node、Docker、Caddy", "dev-env"),
					huh.NewOption("Hermes Agent", "hermes"),
					huh.NewOption("OPS vault 模板", "aiops"),
				).
				Value(&components),
		))
	} else {
		opts.WithDevEnv = false
		opts.WithHermes = false
		opts.WithAIOps = false
		components = nil
	}

	groups = append(groups,
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("核心特性：Skillpack target").
				Options(
					huh.NewOption("universal（推荐，跨 agent）", installer.TargetUniversal),
					huh.NewOption("hermes", installer.TargetHermes),
					huh.NewOption("both", installer.TargetBoth),
				).
				Value(&opts.Target),
			huh.NewSelect[string]().
				Title("核心特性：Skillpack 安装模式").
				Options(
					huh.NewOption("copy（推荐，小白/朋友机器）", installer.ModeCopy),
					huh.NewOption("symlink（开发者机器）", installer.ModeSymlink),
				).
				Value(&opts.Mode),
			huh.NewConfirm().
				Title("先 dry-run？").
				Description("推荐第一次先 dry-run，确认计划后再正式执行。").
				Affirmative("是").
				Negative("否").
				Value(&dryRun),
		),
	)

	form := huh.NewForm(groups...)
	if err := form.Run(); err != nil {
		return opts, false, err
	}

	opts.AddToPath = installer.ChoiceNo
	if addPath {
		opts.AddToPath = installer.ChoiceYes
	}
	if platform == installer.PlatformLinux {
		opts.ProxyTun = useTun
		opts.ResetSources = resetSources
		applyComponents(&opts, components)
	}
	opts.DryRun = dryRun

	if err := opts.Validate(); err != nil {
		return opts, false, err
	}
	plan, err := installer.NewCommandPlan("install.sh", opts)
	if err != nil {
		return opts, false, err
	}
	confirm := huh.NewConfirm().
		Title("确认执行安装计划？").
		Description(fmt.Sprintf("%s\n命令：%s", installer.SummaryForPlatform(opts, platform), plan.RedactedPreview)).
		Affirmative("执行").
		Negative("只打印，不执行").
		Value(&execute)
	if err := confirm.Run(); err != nil {
		return opts, false, err
	}
	return opts, execute, nil
}

func capabilityDescription(platform string) string {
	caps := installer.CapabilitiesForPlatform(platform)
	var core []string
	var addons []string
	for _, cap := range caps {
		if !cap.Supported {
			continue
		}
		line := fmt.Sprintf("- %s：%s", cap.Title, cap.Description)
		if cap.Layer == "core" {
			core = append(core, line)
		} else {
			addons = append(addons, line)
		}
	}
	if len(addons) == 0 {
		addons = append(addons, "- 当前平台不显示 Linux/server 专属附加能力；如需 24/7 systemd/Mihomo/TUN/Docker/Caddy，请使用 Linux 或 WSL 的 install.sh。")
	}
	return "核心特性（本地开机即可使用）：\n" + strings.Join(core, "\n") + "\n\n附加能力（非基础安装必需）：\n" + strings.Join(addons, "\n")
}

func selectedComponents(opts installer.Options) []string {
	components := []string{}
	if opts.WithDevEnv {
		components = append(components, "dev-env")
	}
	if opts.WithHermes {
		components = append(components, "hermes")
	}
	if opts.WithAIOps {
		components = append(components, "aiops")
	}
	return components
}

func applyComponents(opts *installer.Options, components []string) {
	opts.WithDevEnv = false
	opts.WithHermes = false
	opts.WithAIOps = false
	for _, component := range components {
		switch component {
		case "dev-env":
			opts.WithDevEnv = true
		case "hermes":
			opts.WithHermes = true
		case "aiops":
			opts.WithAIOps = true
		}
	}
}
