from ansible.template import Templar
from ansible.playbook.task import Task
from ansible.plugins.action import ActionBase
from ansible.plugins.loader import action_loader

from jinja2 import Environment
from jinja2.exceptions import TemplateSyntaxError
from jinja2.loaders import BaseLoader
from jinja2.nodes import Node, Output, Const, CallBlock
from jinja2.parser import Parser
from jinja2.ext import Extension

"""
{% setindent spaces 8 %}

{% macro foo() %}
	{% indent %}
	function() {+
		{% indent %}
			return [1, 2, 3];+
		{% endindent %}
	}
	{% endindent %}

{% endmacro %}

{+
	{% indent %}
		"root: "true",+
		"values": [+
			{% indent %}{{ foo() }}{% endindent %},+
		],+
	{% endindent %}
}+

{% newline 3 %}
"""


class TemplatePlus(Templar):
    KEEP = "+"

    INDENT = "\ue000"
    NEWLINE = "\ue001"

    POLICY_STYLE = "indent.style"
    POLICY_SIZE = "indent.size"

    def __init__(self, loader: BaseLoader, variables: dict):
        super().__init__(loader, variables)

        self.environment.policies[self.POLICY_STYLE] = "space"
        self.environment.policies[self.POLICY_SIZE] = 4

        self.environment.add_extension(SetIndentExtension)
        self.environment.add_extension(IndentExtension)
        self.environment.add_extension(NewlineExtension)

    def copy_with_new_env(self, environment_class=Environment, **kwargs) -> Templar:
        new_instance = super().copy_with_new_env(environment_class, **kwargs)
        setattr(new_instance, "do_template", self.do_template)

        return new_instance

    def do_template(self, *args, **kwargs) -> str:
        result = super().do_template(*args, **kwargs)
        if not isinstance(result, str):
            return result

        style, size = (self.environment.policies[key] for key in (self.POLICY_STYLE, self.POLICY_SIZE))
        indent = (" " if style == "spaces" else "\t") * size

        return result.replace(self.NEWLINE, "\n").replace(self.INDENT, indent)


class SetIndentExtension(Extension):
    tags = {"setindent"}

    def parse(self, parser: Parser) -> Node:
        lineno = next(parser.stream).lineno

        indent_style = parser.parse_expression()
        if indent_style.name not in ("tabs", "spaces"):
            raise TemplateSyntaxError("Expected indent style to be either 'tabs' or 'spaces'.", lineno)
        self.environment.policies[TemplatePlus.POLICY_STYLE] = indent_style.name

        indent_size = parser.parse_expression()
        if not (0 < indent_size.value <= 8):
            raise TemplateSyntaxError("Indentation size must be bigger than 0 and less than 9.", lineno)
        self.environment.policies[TemplatePlus.POLICY_SIZE] = indent_size.value

        return Output("", lineno=lineno)


class NewlineExtension(Extension):
    tags = {"newline"}

    def parse(self, parser: Parser) -> Node:
        lineno = next(parser.stream).lineno

        count_token = parser.stream.next_if("integer")
        count = 1 if count_token is None else count_token.value
        if not (0 < count <= 10):
            raise TemplateSyntaxError("Newline counter must be bigger than 0 and less than 10.")

        return Output([Const(TemplatePlus.NEWLINE * count)], lineno=lineno)


class IndentExtension(Extension):
    tags = {"indent"}

    def preprocess(self, source: str, name: str | None, filename: str | None = None) -> str:
        lines = []
        for line in source.splitlines():
            line = line.replace("\n", "").replace("\t", "")
            if line.endswith(TemplatePlus.KEEP):
                lines.append(f"{line[:-1]}{TemplatePlus.NEWLINE}")
            else:
                lines.append(line)

        # TODO: another placeholder or keep the newline
        # that needs to be replaced to none afterwards.
        # Lua inline array would say thank you :)
        return "".join(lines)

    def parse(self, parser: Parser) -> Node:
        lineno = next(parser.stream).lineno

        size_token = parser.stream.next_if("integer")
        size = 1 if size_token is None else size_token.value

        body = parser.parse_statements(["name:endindent"], drop_needle=True)

        return CallBlock(
            self.call_method("_wrapped_indent", args=[Const(size)]),
            [],
            [],
            body,
            lineno=lineno,
        )

    def _wrapped_indent(self, size, caller):
        indent = TemplatePlus.INDENT * size

        return TemplatePlus.NEWLINE.join(
            (line if not line else f"{indent}{line}" for line in str(caller()).split(TemplatePlus.NEWLINE))
        )


class ActionModule(ActionBase):
    def run(self, tmp: None = None, task_vars: dict = None):
        templar = TemplatePlus(self._loader, task_vars)
        task = Task.load(
            {"ansible.builtin.template": self._task.args},
            block=self._task,
            loader=self._loader,
            variable_manager=self._task.get_variable_manager(),
        )

        action = action_loader.get(
            "ansible.builtin.template",
            task=task,
            connection=self._connection,
            play_context=self._play_context,
            loader=self._loader,
            templar=templar,
            shared_loader_obj=self._shared_loader_obj,
        )
        return action.run(task_vars=task_vars)
