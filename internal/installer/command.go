package installer

import (
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const Redacted = "<redacted>"

type CommandPlan struct {
	Script          string   `json:"script"`
	Argv            []string `json:"argv"`
	Preview         string   `json:"preview"`
	RedactedPreview string   `json:"redacted_preview"`
}

func NewCommandPlan(script string, options Options) (CommandPlan, error) {
	args, err := BuildInstallArgs(options)
	if err != nil {
		return CommandPlan{}, err
	}
	cmd := append([]string{ShellExecutable(), script}, args...)
	redacted := append([]string(nil), cmd...)
	for i := 0; i < len(redacted)-1; i++ {
		if redacted[i] == "--proxy-subscription-url" {
			redacted[i+1] = Redacted
		}
	}
	return CommandPlan{
		Script:          script,
		Argv:            args,
		Preview:         ShellJoin(cmd),
		RedactedPreview: ShellJoin(redacted),
	}, nil
}

func ShellExecutable() string {
	if runtime.GOOS == "windows" {
		return "bash"
	}
	return "bash"
}

func ShellJoin(args []string) string {
	quoted := make([]string, len(args))
	for i, arg := range args {
		quoted[i] = ShellQuote(arg)
	}
	return strings.Join(quoted, " ")
}

func ShellQuote(s string) string {
	if s == "" {
		return "''"
	}
	if isShellSafe(s) {
		return s
	}
	return "'" + strings.ReplaceAll(s, "'", "'\\''") + "'"
}

func isShellSafe(s string) bool {
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') {
			continue
		}
		switch r {
		case '_', '-', '.', '/', ':', '=', '+', ',', '~':
			continue
		default:
			return false
		}
	}
	return true
}

func DiscoverScript(explicit string) (string, error) {
	if explicit != "" {
		abs, err := filepath.Abs(explicit)
		if err != nil {
			return "", err
		}
		st, err := os.Stat(abs)
		if err != nil {
			return "", err
		}
		if st.IsDir() {
			return "", fmt.Errorf("script path is a directory: %s", abs)
		}
		return abs, nil
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for dir := cwd; ; dir = filepath.Dir(dir) {
		candidate := filepath.Join(dir, "install.sh")
		if st, err := os.Stat(candidate); err == nil && !st.IsDir() {
			return candidate, nil
		}
		next := filepath.Dir(dir)
		if next == dir {
			break
		}
	}
	return "", os.ErrNotExist
}
