from io import StringIO
import json

from doit.cmd_graph import Graph
from doit.control import TaskControl
from doit.task import Task
from tests.conftest import tasks_sample, CmdFactory


class TestCmdGraph:

    def test_text_output_includes_dependencies(self):
        output = StringIO()
        tasks = tasks_sample()
        tasks.append(Task("t4", None, task_dep=['g1.b', 'g1.a']))
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks)

        cmd_graph._execute()

        text = output.getvalue()
        assert "g1\n" in text
        assert "  task_dep: g1.a, g1.b" in text
        assert "t3\n" in text
        assert "  task_dep: t1" in text
        assert "t4\n" in text
        assert "  task_dep: g1.a, g1.b" in text

    def test_json_output(self):
        output = StringIO()
        tasks = tasks_sample()
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks)

        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        g1_entry = next(item for item in data if item['name'] == 'g1')
        assert g1_entry['task_dep'] == ['g1.a', 'g1.b']
        assert g1_entry['setup'] == []

    def test_selection_limits_graph(self):
        output = StringIO()
        setup = Task("setup_task", None)
        t1 = Task("t1", None, setup=['setup_task'])
        tasks = [setup, t1]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks,
                               sel_tasks=['t1'], sel_default_tasks=False)

        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}
        assert 'setup_task' in names
        assert names == {'t1', 'setup_task'}

    def test_actions_are_not_executed(self):
        output = StringIO()
        marker = []
        task = Task("sample", [lambda: marker.append('ran')])
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=[task])

        cmd_graph._execute()

        assert marker == []

    def test_subtasks(self):
        output = StringIO()
        tasks = tasks_sample()
        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['g1'])

        cmd_graph._execute()

        text = output.getvalue()
        assert "g1.a\n" in text
        assert "g1.b\n" in text
