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
        s3 = Task("s3", None)
        d2 = Task("d2", None, setup=['s3'])
        s2 = Task("s2", None)
        d1 = Task("d1", None)
        s1 = Task("s1", None, task_dep=['d1'], setup=['s2'])
        t1 = Task("t1", None, setup=['s1'], task_dep=['d2'])
        other = Task("other", None)
        
        tasks = [s3, d2, s2, d1, s1, t1, other]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks,
                               sel_tasks=['t1'], sel_default_tasks=False)

        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}
        expected = {'t1', 's1', 'd1', 's2', 'd2', 's3'}
        assert names == expected

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
