#
# Nushell Config File
#
# based on the default config from 0.94.2
#

#
# Carapace completer
#
$env.CARAPACE_BRIDGES = "zsh"
$env.CARAPACE_HIDDEN = 1
$env.CARAPACE_LENIENT = 1
$env.CARAPACE_MATCH = 1
$env.CARAPACE_LOG = 0

#Get an environment variable.
def --env get-env [name] {
    $env | get $name 
}

#Set an environment variable.
def --env set-env [name, value] {
    load-env { $name: $value }
}

#Hide an environment variable.
def --env unset-env [name] {
    hide-env $name
}


#
# Zoxide
#

#Zoxide, a smarter cd command.  
def --env z [...rest:string] {
    cd (^zoxide query --exclude $env.PWD -- ...$rest | str trim -r -c "\n")
}

#Zoxide, a smarter cd command (interactive selection). 
def --env zi [...rest:string] {
    cd (^zoxide query --exclude $env.PWD --interactive -- ...$rest | str trim -r -c "\n")
}


#
# Altuin
#
$env.ATUIN_SESSION = (atuin uuid)
$env.ATUIN_LOG = error
hide-env -i ATUIN_HISTORY_ID


#
# Mise
#
$env.MISE_SHELL = "nu"

#A tool for managing runtime versions.
def --wrapped --env mise [...rest: string] {
    if (($rest | is-empty) or ("-h" in $rest) or ("--help" in $rest)) {
        return (^/usr/bin/mise ...$rest)
    }

    match $rest.0 {
        "activate" => {
           $env.MISE_SHELL = "nu"
        },
        "hook-env" | "deactivate" | "shell" => {
            let parsed = (^/usr/bin/mise ...$rest) | from csv --noheaders;

            $parsed
                | where column1 == set
                | reduce -f {} {|it, acc|
                    let val = if ($it.column2 == "PATH") {
                        ($it.column3 | split row (char esep))
                    } else {
                        $it.column3
                    }

                    $acc | upsert $it.column2 $val
                }
                | load-env
            hide-env ...($parsed | where column1 == hide | each {|it| $it.column2 })

            if ($rest.0 == "deactivate") {
                hide-env ...($env | columns | filter {|$k| $k | str contains "MISE" })
            }
        },
        _ => {
            ^/usr/bin/mise ...$rest
        },
    }
}


#
# Running inside anonymous closure to prevent
# variables being exposed to the shell
#
do --env {
    let completer = {|spans|
        let ctx = $spans | first
        let rest = $spans | skip

        match $ctx {
            "z" | "zi" => (zoxide query --exclude $env.PWD --list ...$rest | lines),

            _ => (carapace $ctx nushell ...$spans  | from json)
            #
            # If aliases to non-builtin commands (such as ls) is expected to be used 
            #
            # _ => {
            #     let subs = (
            #         scope aliases
            #             | where name == $ctx
            #             | get -i $.0.expansion
            #             | default $ctx
            #             | split row " "
            #     )
            #     (carapace ($subs | first) nushell ...($subs | skip) ...$rest  | from json)
            # },
        }
    }

    #
    # Nord theme with some unpopular decisions (e.g. cyan for strings).
    #
    let theme = {
        separator: dark_gray,
        leading_trailing_space_bg: { bg: dark_gray },
        search_result: { bg: black fg: cyan attr: b },

        header: blue_bold,
        row_index: dark_gray,
        hints: dark_gray,

        # [{}, [], {?}, $.one.two]
        record: yellow,
        list: yellow,
        block: yellow,
        cell-path: yellow,

        bool: purple_bold,
        int: purple_bold,
        float: purple_bold,
        range: purple_bold,
        binary: purple_bold,

        filesize: green_bold,
        duration: green_bold,
        date: green_bold,

        string: cyan,

        nothing: white,
        empty: white,

        shape_and: blue_bold,
        shape_or: blue_bold,
        shape_operator: blue_bold,
        shape_keyword: blue_bold,
        shape_internalcall: blue_bold,
        shape_nothing: blue_bold,

        shape_pipe: dark_gray_bold,
        shape_signature: light_cyan_bold,
        shape_redirection: yellow_bold,
        
        shape_int: purple_bold,
        shape_bool: purple_bold,
        shape_binary: purple_bold,
        shape_range: purple_bold,
        shape_float: purple_bold,
        
        shape_record: dark_gray_bold,
        shape_block: dark_gray_bold,
        shape_closure: dark_gray_bold,
        shape_custom: dark_gray_bold,
        shape_table: dark_gray_bold,
        shape_list: dark_gray_bold,
        shape_matching_brackets: dark_gray_bold,

        shape_datetime: green_bold,
        shape_garbage: red_bold,

        shape_vardecl: white,
        shape_variable: white,
        shape_match_pattern: white,

        shape_directory: light_cyan,
        shape_filepath: light_cyan,
        shape_globpattern: light_cyan,

        shape_string: cyan,
        shape_string_interpolation: cyan,

        shape_raw_string: yellow,
        shape_literal: yellow_bold,

        shape_flag: green,

        shape_external: red,
        shape_external_resolved: blue_bold,
        shape_externalarg: cyan,
    }

    #
    # Keybindings
    #
    let keybindings = [
        #
        # Vim (Reedline) keybindings
        #
        # w      -> Word
        # 0      -> Line start0.
        # $      -> Line end
        # f      -> (?) Right until char
        # t      -> (?) Right before char
        # F      -> (?) Left until char
        # T      -> (?) Left before char
        #
        # d      -> Delete
        # p      -> Paste after
        # P      -> Paste before
        # h      -> Move left
        # l      -> Move right
        # j      -> Move down
        # k      -> Move up
        # w      -> Move word right
        # b      -> Move word left
        # i      -> Enter Vi insert at current char
        # a      -> Enter Vi insert after char
        # 0      -> Move to start of line
        # ^      -> Move to start of line
        # $      -> Move to end of line
        # u      -> Undo
        # c      -> Change
        # x      -> Delete char
        # s      -> History search (Delete char + enter insert mode)
        # D      -> Delete to end
        # A      -> Append to end
        #
        #
        { modifier: shift, keycode: char_b, mode: [vi_normal], event: { edit: MoveWordLeft, select: true } },
        { modifier: shift, keycode: char_w, mode: [vi_normal], event: { edit: MoveWordRight, select: true} },
        
        { modifier: shift, keycode: char_h, mode: [vi_normal], event: { edit: MoveLeft, select: true } },
        { modifier: shift, keycode: char_l, mode: [vi_normal], event: { edit: MoveRight, select: true } },
        { modifier: shift, keycode: char_j, mode: [vi_normal], event: { edit: MoveToLineEnd, select: true } },
        { modifier: shift, keycode: char_k, mode: [vi_normal], event: { edit: MoveToLineStart, select: true } },
         
        { modifier: none, keycode: char_f, mode: [vi_normal], event: { edit: MoveToStart } },
        { modifier: shift, keycode: char_f, mode: [vi_normal], event: { edit: MoveToStart, select: true } },
        { modifier: none, keycode: char_g, mode: [vi_normal], event: { edit: MoveToEnd } },
        { modifier: shift, keycode: char_g, mode: [vi_normal], event: { edit: MoveToEnd, select: true } },
    
        #
        # Emacs-Bash-like keywords
        #
        { modifier: alt, keycode: char_a, mode: [vi_normal, vi_insert], event: { edit: MoveToLineStart } },
        { 
            modifier: alt_shift, keycode: char_a, mode: [vi_normal, vi_insert],
            event: { edit: MoveToLineStart, select: true } 
        },
        { modifier: alt, keycode: char_e, mode: [vi_normal, vi_insert], event: { edit: MoveToLineEnd } },
        { 
            modifier: alt_shift, keycode: char_e, mode: [vi_normal, vi_insert],
            event: { edit: MoveToLineEnd, select: true } 
        },
    
        { modifier: alt, keycode: "char_,", mode: [vi_normal, vi_insert], event: { edit: MoveToStart } },
        { 
            modifier: alt_shift, keycode: "char_,", mode: [vi_normal, vi_insert],
            event: { edit: MoveToStart, select: true }
        },
        { modifier: alt, keycode: "char_.", mode: [vi_normal, vi_insert], event: { edit: MoveToEnd } },
        {
            modifier: alt_shift, keycode: "char_.", mode: [vi_normal, vi_insert],
            event: { edit: MoveToEnd, select: true }
        },
            
        { modifier: alt, keycode: char_w, mode: [vi_normal, vi_insert], event: { edit: BackspaceWord } },
    
        { modifier: alt, keycode: char_k, mode: [vi_normal, vi_insert], event: { edit: ClearToLineEnd } },
        {
            modifier: alt, keycode: char_d, mode: [vi_normal, vi_insert],
            event: [ { edit: MoveToLineStart } { edit: ClearToLineEnd }]
        },
    
        { modifier: alt, keycode: left, mode: [vi_normal, vi_insert], event: { edit: MoveWordLeft } },
        {
            modifier: alt_shift, keycode: left, mode: [vi_normal, vi_insert],
            event: { edit: MoveWordLeft, select: true }
        },
        { modifier: alt, keycode: right, mode: [vi_normal, vi_insert], event: { edit: MoveWordRight } },
        {
            modifier: alt_shift, keycode: right, mode: [vi_normal, vi_insert],
            event: { edit: MoveWordRight, select: true }
        },
        { modifier: alt, keycode: up, mode: [vi_normal, vi_insert], event: { send: Up } },
        {
            modifier: alt_shift, keycode: up, mode: [vi_normal, vi_insert],
            event: { edit: MoveToLineStart, select: true }
        },
        { modifier: alt, keycode: down, mode: [vi_normal, vi_insert], event: { send: Down } },
        {
            modifier: alt_shift, keycode: down, mode: [vi_normal, vi_insert],
            event: { edit: MoveToLineEnd, select: true }
        },
    
        #
        # Common (browser/gui like) bindings
        #
    
        {
            modifier: none, keycode: up, mode: [vi_normal, vi_insert],
            event: { until: [ { send: MenuUp }, { send: Up } ] }
        },
        {
            modifier: control, keycode: up, mode: [vi_normal, vi_insert],
            event: [ { send: Up }, { send: Up }, { send: Up } ],
        },
        { modifier: shift, keycode: up, mode: [vi_normal, vi_insert], event: { edit: MoveToLineEnd, select: true } },
    
        {
            modifier: none, keycode: down, mode: [vi_normal, vi_insert], 
            event: { until: [ { send: MenuDown }, { send: Down } ] },
        },
        {
            modifier: control, keycode: down, mode: [vi_normal, vi_insert],
            event: [ { send: Down }, { send: Down }, { send: Down } ],
        },
        {
            modifier: shift, keycode: down, mode: [vi_normal, vi_insert],
            event: { edit: MoveToLineStart, select: true }
        },
    
        {
            modifier: none, keycode: left, mode: [vi_normal, vi_insert], 
            event: { until: [ { send: MenuLeft }, { send: Left } ] },
        },
        { modifier: shift, keycode: left, mode: [vi_normal, vi_insert], event: { edit: MoveLeft, select: true } },
        {
            modifier: control, keycode: left, mode: [vi_normal, vi_insert], 
            event: [ { edit: MoveLeft }, { edit: MoveLeft }, { edit: MoveLeft } ],
        },
        {
            modifier: control_shift, keycode: left, mode: [vi_normal, vi_insert], 
            event: [
                { edit: MoveLeft, select: true }, { edit: MoveLeft, select: true }, { edit: MoveLeft, select: true }
            ],
        },
    
        {
            modifier: none, keycode: right, mode: [vi_normal, vi_insert],
            event: { until: [ { send: HistoryHintComplete }, { send: MenuRight }, { send: Right } ] },
        },
        {
            modifier: shift, keycode: right, mode: [vi_normal, vi_insert], 
            event: { until: [ { edit: MoveRight, select: true } ] },
        },
        {
            modifier: control, keycode: right, mode: [vi_normal, vi_insert], 
            event: [ { edit: MoveRight }, { edit: MoveRight }, { edit: MoveRight } ],
        },
        {
            modifier: control_shift, keycode: right, mode: [vi_normal, vi_insert], 
            event: [ 
                { edit: MoveRight, select: true },
                { edit: MoveRight, select: true },
                { edit: MoveRight, select: true }
            ],
        },
    
        {
            modifier: none, keycode: tab, mode: [vi_normal, vi_insert],
            event: { until: [ { send: menu, name: completion_menu }, { send: menunext }, { edit: complete } ] },
        },
        { modifier: shift, keycode: backtab, mode: [vi_normal, vi_insert], event: { send: MenuPrevious } },
    
        { modifier: control, keycode: char_z, mode: [vi_normal, vi_insert], event: { edit: Undo } },
        { modifier: control_shift, keycode: char_z, mode: [vi_normal, vi_insert], event: { edit: Redo } },
        { modifier: control, keycode: char_y, mode: [vi_normal, vi_insert], event: { edit: Redo } },
        { modifier: control, keycode: char_r, mode: [vi_normal, vi_insert], event: { edit: Redo } },
        { 
            modifier: control_shift, keycode: char_c, mode: [vi_normal, vi_insert],
            event: { edit: CopySelectionSystem } 
        },
        { modifier: control, keycode: char_v, mode: [vi_normal, vi_insert], event: { edit: pastesystem } },
        { modifier: control, keycode: char_x, mode: [vi_normal, vi_insert], event: { edit: cutselectionsystem } },
    
        { modifier: none, keycode: escape, mode: [vi_normal, vi_insert], event: { send: Esc } },
        { modifier: none, keycode: enter, mode: [vi_normal, vi_insert], event: { send: Enter } },
        { modifier: control, keycode: char_c, mode: [vi_normal, vi_insert], event: { send: CtrlC } },
        { modifier: control, keycode: char_l, mode: [vi_normal, vi_insert], event: { send: ClearScreen } },
        { modifier: control, keycode: char_o, mode: [vi_normal, vi_insert], event: { send: OpenEditor } }
        { modifier: control, keycode: char_a, mode: [vi_normal, vi_insert], event: { edit: SelectAll } },
    
        { modifier: none, keycode: backspace, mode: [vi_normal, vi_insert], event: { edit: Backspace } },
        { modifier: control, keycode: backspace, mode: [vi_normal, vi_insert], event: { edit: BackspaceWord } },
        { modifier: control, keycode: char_h, mode: [vi_normal, vi_insert], event: { edit: Delete } },
        { modifier: control, keycode: delete, mode: [vi_normal, vi_insert], event: { edit: DeleteWord } },

        #
        # Atuin
        #
        {
            modifier: control, keycode: char_f, mode: [vi_normal, vi_insert],
            event: {
                send: executehostcommand,
                cmd: "# nushell-ignore-history\ncommandline edit (^atuin search --interactive e>| str trim)",
            },
        },
    ]
    #
    # A particular keybinding is only disabled if its `event` is explicitly set to null.
    # Commenting or omitting keybinding entirely will still fall back to the `keybindings default`.
    #
    # Please use the snippet below to generate config entries to disable default keybindings except those that are
    # already listed in the $keybindings.
    #
    # Although it is possible to run this snipped on every run, it gives a considerable overhead for about 100ms.
    #
    # print (
    #     keybindings default 
    #     | each {|k|
    #         {
    #             modifier: (
    #                 $k
    #                 | get modifier
    #                 | str replace --regex r#'KeyModifiers\((.*)\)'# "$1"
    #                 | str replace " | " "_"
    #                 | str replace "0x0" "none"
    #                 | str downcase
    #             ),
    #             keycode: (
    #                 $k
    #                 | get code
    #                 | str replace --regex r#'Char\('(\w)'\)'# "char_$1"
    #                 | str downcase
    #             ),
    #         }
    #     }
    #     | uniq
    #     | where {|k|
    #         not ($keybindings | any {|$kk| 
    #             ($kk.keycode == $k.keycode) and ($kk.modifier == $k.modifier)
    #         })
    #     }
    #     | each {|$k| 
    #         $"{ modifier: ($k.modifier), keycode: ($k.keycode), mode: [emacs, vi_insert, vi_normal], event: null },"
    #     }
    #     | str join "\n"
    # )
    #
    let removed_keybindings = [
        { modifier: none, keycode: F1, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_q, mode: [emacs, vi_insert, vi_normal], event: null },

        { modifier: none, keycode: end, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: none, keycode: esc, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: none, keycode: home, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: backspace, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: char_b, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: char_c, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: char_f, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: char_l, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: char_m, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: char_u, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: alt, keycode: delete, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_b, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_d, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_e, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_f, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_g, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_h, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_k, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_n, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_p, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_t, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_u, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: char_w, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: delete, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: end, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: control, keycode: home, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: char_a, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: char_c, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: char_v, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: char_x, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: end, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: home, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: left, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift_control, keycode: right, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift, keycode: end, mode: [emacs, vi_insert, vi_normal], event: null },
        { modifier: shift, keycode: home, mode: [emacs, vi_insert, vi_normal], event: null },
    ]

    $env.config = {
        ls: {
            use_ls_colors: true,
            clickable_links: true,
        },
    
        rm: {
            always_trash: false,
        }
    
        table: {
            mode: compact,
            index_mode: always,
            show_empty: true,
            padding: { left: 1, right: 1 },
            trim: {
                methodology: wrapping,
                truncating_suffix: "...",
            }
            header_on_separator: false,
        },
    
        datetime_format: {
            normal: '%d-%b-%Y %r %:z',
            table: '%d-%b-%Y %r',
        },
    
        explore: {
            status_bar_background: { bg: black, fg: light_cyan },
            command_bar_text: white,
            highlight: yellow_bold,
            status: {
                error: red_bold,
                warn: yellow_bold,
                info: light_cyan_bold,
            },
            table: {
                split_line: dark_gray,
                selected_cell: { bg: dark_gray },
                selected_row: {},
                selected_column: {},
            },
        },
    
        history: {
            max_size: 100_000,
            sync_on_enter: false,
            file_format: sqlite,
            isolation: true,
        },
    
        completions: {
            case_sensitive: false,
            quick: true,
            partial: true,
            algorithm: prefix,
            external: {
                enable: true,
                max_results: 100,
                completer: $completer,
            }
            use_ls_colors: true,
        },
    
        filesize: {
            metric: true,
            format: auto,
        },
    
        cursor_shape: { 
            vi_insert: line,
            vi_normal: underscore,
        },
    
        shell_integration: {
            osc2: true,
            osc7: true,
            osc8: true,
            osc9_9: true,
            osc133: true,
            osc633: true,
            reset_application_mode: true,
        },
    
        color_config: $theme,
    
        show_banner: false,
        error_style: fancy,
        use_grid_icons: true,
        footer_mode: never,
        float_precision: 3,
        use_ansi_coloring: true,
        bracketed_paste: true,
        edit_mode: vi,
        render_right_prompt_on_last_line: false,
        use_kitty_protocol: true,
        highlight_resolved_externals: true,
        recursion_limit: 50,
    
        plugin_gc: {
            default: {
                enabled: true,
                stop_after: 10sec,
            },
        },
    
        hooks: {
            pre_prompt: [
                {
                    condition: { 'ATUIN_HISTORY_ID' in $env },
                    code: {
                        ^atuin history end $"--exit=($env.LAST_EXIT_CODE | default 1)" -- $env.ATUIN_HISTORY_ID

                        hide-env ATUIN_HISTORY_ID
                    },
                },
                {
                    condition: { "MISE_SHELL" in $env },
                    code: { mise hook-env --shell=nu },
                },
            ],
            pre_execution: [
                {
                    condition: { 
                        let cmd = (commandline)

                        not ($cmd | is-empty) and not ($cmd | str starts-with "# nushell-ignore-history")
                    },
                    code: { $env.ATUIN_HISTORY_ID = (atuin history start -- (commandline)) },                
                },
            ],
            env_change: {
                PWD: [{|_, dir| ^zoxide add -- $dir }],
            },
            display_output: "if (term size).columns >= 100 { table -e } else { table }",
            command_not_found: { null },
        },
    
        menus: [
            {
                name: completion_menu,
                only_buffer_difference: false,
                marker: $" (ansi reset)\u{f0d0}  ",
                type: {
                    layout: columnar,
                    columns: 4,
                    col_padding: 2,
                },
                style: {
                    text: blue,
                    description_text: cyan,
                    match_text: light_cyan,
                    selected_text: { bg: light_cyan, fg: black, attr: b },
                    selected_match_text: { bg: light_cyan, fg: black, attr: b },
                },
            },
        ],
    
        keybindings: ($removed_keybindings | append $keybindings),
    }
}

^fastfetch
