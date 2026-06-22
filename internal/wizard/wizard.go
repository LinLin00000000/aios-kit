package wizard

import (
	"fmt"

	"github.com/charmbracelet/huh"

	"github.com/LinLin00000000/aios-kit/internal/installer"
)

func Run(opts installer.Options) (installer.Options, bool, error) {
	addPath := opts.AddToPath != installer.ChoiceNo
	useTun := opts.ProxyTun
	resetSources := opts.ResetSources
	dryRun := opts.DryRun
	execute := false
	components := selectedComponents(opts)

	form := huh.NewForm(
		huh.NewGroup(
			huh.NewInput().
				Title("AIOS 安装根目录").
				Description("默认 ~/aios；支持 ~，真实展开由 install.sh 处理。").
				Value(&opts.Root),
			huh.NewConfirm().
				Title("把 ~/aios/bin 加入 PATH？").
				Affirmative("加入").
				Negative("不加入").
				Value(&addPath),
		),
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("代理 / 网络模式").
				Description("auto 会先测试直连，失败时再安装 Mihomo。").
				Options(
					huh.NewOption("auto：自动检测（推荐）", installer.ChoiceAuto),
					huh.NewOption("yes：强制安装/配置代理", installer.ChoiceYes),
					huh.NewOption("no：不配置代理", installer.ChoiceNo),
				).
				Value(&opts.Proxy),
			huh.NewConfirm().
				Title("开启 Mihomo TUN？").
				Description("Linux 服务器默认推荐开启；Windows/macOS 后续会逐步完善平台策略。私有订阅可安装后再配置。").
				Affirmative("开启").
				Negative("关闭").
				Value(&useTun),
			huh.NewConfirm().
				Title("恢复 apt/npm/pip/Docker 官方源？").
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
		),
		huh.NewGroup(
			huh.NewMultiSelect[string]().
				Title("选择要安装/检查的组件").
				Description("空格复选，上下键移动，回车确认。").
				Options(
					huh.NewOption("开发环境：Python/UV、Node、Docker、Caddy", "dev-env"),
					huh.NewOption("Hermes Agent", "hermes"),
					huh.NewOption("OPS vault 模板", "aiops"),
				).
				Value(&components),
		),
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Skillpack target").
				Options(
					huh.NewOption("universal（推荐，跨 agent）", installer.TargetUniversal),
					huh.NewOption("hermes", installer.TargetHermes),
					huh.NewOption("both", installer.TargetBoth),
				).
				Value(&opts.Target),
			huh.NewSelect[string]().
				Title("Skillpack 安装模式").
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

	if err := form.Run(); err != nil {
		return opts, false, err
	}

	opts.AddToPath = installer.ChoiceNo
	if addPath {
		opts.AddToPath = installer.ChoiceYes
	}
	opts.ProxyTun = useTun
	opts.ResetSources = resetSources
	opts.DryRun = dryRun
	applyComponents(&opts, components)

	if err := opts.Validate(); err != nil {
		return opts, false, err
	}
	plan, err := installer.NewCommandPlan("install.sh", opts)
	if err != nil {
		return opts, false, err
	}
	confirm := huh.NewConfirm().
		Title("确认执行安装计划？").
		Description(fmt.Sprintf("%s\n命令：%s", installer.Summary(opts), plan.RedactedPreview)).
		Affirmative("执行").
		Negative("只打印，不执行").
		Value(&execute)
	if err := confirm.Run(); err != nil {
		return opts, false, err
	}
	return opts, execute, nil
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
