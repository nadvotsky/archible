#!/usr/bin/env nu

#
# This is a simple script that parses the current parameters of the
#  `snd_hda_intel` driver and according to these values formats the name of the
#  output of the following `amixer` and `arecord` invocations.
#

let parameters = [
    {
        name: "enable_msi",
        type: "int",
        constraint: {|v| $v in [0, 1] },
        default: "def",
    },
    {
        name: "position_fix",
        type: "int",
        constraint: {|v| $v in 1..6 },
        default: "no",
    },
    {
        name: "model",
        type: "string",
        constraint: {|v| not ($v | parse "asus-mode{mode}" | is-empty) },
        default: "def",
    },
]

let output = $parameters
    | each {|schema|
        let raw_param = open -r $"/sys/module/snd_hda_intel/parameters/($schema.name)"
            | decode utf-8
            | split row ","
            | first
        try {
            mut parsed = match ($schema.type) {
                "int" => ($raw_param | into int)
                "bool" => ($raw_param | into bool)
                "float" => ($raw_param | into float)
                _ => ($raw_param)
            }
            if not (do $schema.constraint $parsed) {
                $parsed = $schema.default
            }

            $"($schema.name | split row "_" | last):($parsed)"
        } catch {|err|
            print $"An error occured: ($err.msg)"
            exit
        }
    }
    | str join "+"

print $"Exporting mixers information ($output)"
^amixer -c 0 scontents | save -f $"($output).txt"

print $"Recording sample ($output)"
^arecord -r 48000 -f S32_LE -c 2 -d 10 -D hw:0,0 $"($output).wav"
