from io import StringIO
import json

from doit.cmd_graph import Graph
from doit.task import Task
from tests.conftest import tasks_sample, CmdFactory


class TestCmdGraph:

    def test_text_output_includes_dependencies(self):
        output = StringIO()
        tasks = tasks_sample()
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks)

        cmd_graph._execute()

        text = output.getvalue()
        assert text == ""

    def test_json_output(self):
        output = StringIO()
        tasks = tasks_sample()
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks)

        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        assert data == []

    def test_selection_limits_graph(self):
        output = StringIO()
        tasks = tasks_sample()
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks,
                               sel_tasks=['t3'], sel_default_tasks=False)

        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}
        assert names == set()

    def test_actions_are_not_executed(self):
        output = StringIO()
        marker = []
        task = Task("sample", [lambda: marker.append('ran')])
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=[task])

        cmd_graph._execute()

        assert marker == []

