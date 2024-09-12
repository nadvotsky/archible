#
# Nushell Environment Config File
#
# based on the default config from 0.94.2
#

#
# Starship configuration
#
$env.STARSHIP_LOG = "error"
$env.STARSHIP_CACHE = "/tmp"
$env.PROMPT_COMMAND = {||
    (
        ^/usr/bin/starship prompt
        $"--cmd-duration=($env.CMD_DURATION_MS)"
        $"--status=($env.LAST_EXIT_CODE)"
        $"--terminal-width=((term size).columns)"
    )
}

$env.PROMPT_COMMAND_RIGHT = null
$env.PROMPT_INDICATOR = null

$env.PROMPT_INDICATOR_VI_INSERT = {|| $"(ansi ligr) \u{f17b5} (ansi reset) " }
$env.PROMPT_INDICATOR_VI_NORMAL = {|| $"(ansi ligr) \u{f090c} (ansi reset) " }
$env.PROMPT_MULTILINE_INDICATOR = {|| $"(ansi ligr) \u{ea7c} (ansi reset) " }

#
# Specifies how environment variables are:
# - converted from a string to a value on Nushell startup (from_string)
# - converted from a value back to a string when running external commands (to_string)
# Note: The conversions happen *after* config.nu is loaded
#
$env.ENV_CONVERSIONS = {
    "PATH": {
        from_string: { |s| $s | split row (char esep) | path expand --no-symlink }
        to_string: { |v| $v | path expand --no-symlink | str join (char esep) }
    }
}

$env.PATH = (["~/.local/bin", $env.PATH] | str join (char esep))

#
# GNUPG SSH Agent configuration
#
$env.GPG_TTY = (tty)
$env.SSH_AUTH_SOCK = (gpgconf --list-dirs agent-ssh-socket)

#
# micro editor configuration
#
$env.VISUAL = "micro"
$env.EDITOR = "micro"

#
# bat pager configuration
#
$env.BAT_THEME = "Nord"
$env.PAGER = "bat"
$env.MANPAGER = "bat --style=grid"

#
# LS_COLORS theming
#
$env.LS_COLORS = (vivid generate nord)

#
# fzf theming
#
$env.FZF_DEFAULT_OPTS = ([
    "--color=fg:-1,bg:-1,hl:blue",
    "--color=fg+:-1,bg+:black,hl+:blue",
    "--color=info:bright-cyan,prompt:red,pointer:magenta",
    "--color=marker:magenta,spinner:yellow,header:green",
    "--color=border:bright-black,label:bright-cyan",
] | str join " ")

#
# aliases
#
alias l = ls -a
