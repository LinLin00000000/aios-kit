package installer

import (
	"errors"
	"io"
	"os"
	"os/exec"
)

type Runner struct {
	Stdout io.Writer
	Stderr io.Writer
}

func (r Runner) Run(script string, args []string) error {
	if script == "" {
		return errors.New("script path is required")
	}
	cmd := exec.Command(ShellExecutable(), append([]string{script}, args...)...)
	if r.Stdout != nil {
		cmd.Stdout = r.Stdout
	} else {
		cmd.Stdout = os.Stdout
	}
	if r.Stderr != nil {
		cmd.Stderr = r.Stderr
	} else {
		cmd.Stderr = os.Stderr
	}
	cmd.Stdin = os.Stdin
	return cmd.Run()
}
