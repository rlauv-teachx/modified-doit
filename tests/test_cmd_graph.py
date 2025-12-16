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

        assert 'other' not in names

        t1_entry = next(e for e in data if e['name'] == 't1')
        assert t1_entry['setup'] == ['s1']
        assert t1_entry['task_dep'] == ['d2']

        d2_entry = next(e for e in data if e['name'] == 'd2')
        assert d2_entry['setup'] == ['s3']

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

        assert "g1\n" in text

        assert "task_dep: g1.a, g1.b" in text


class TestCmdGraphEdgeCases:
    """Tests for edge cases and potential issues in graph command."""

    def test_subtask_with_colon_separator(self):
        """Test lazy materialization with standard colon separator (production case).

        The _lazy_materialise method has an optimization path for ':' separator
        but tests/conftest.py uses '.' separator. This test verifies the colon
        separator path works correctly.
        """
        output = StringIO()
        parent = Task("group", None, has_subtask=True, task_dep=['group:sub1', 'group:sub2'])
        sub1 = Task("group:sub1", [""], subtask_of='group')
        sub2 = Task("group:sub2", [""], subtask_of='group')
        tasks = [parent, sub1, sub2]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['group'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'group', 'group:sub1', 'group:sub2'}

        parent_entry = next(e for e in data if e['name'] == 'group')
        assert sorted(parent_entry['task_dep']) == ['group:sub1', 'group:sub2']

        sub1_entry = next(e for e in data if e['name'] == 'group:sub1')
        assert sub1_entry['task_dep'] == []
        assert sub1_entry['setup'] == []

    def test_missing_dependency_raises_error(self):
        """Test that missing task dependencies are caught by TaskControl.

        TaskControl validates that all task_dep references exist, raising
        InvalidTask if a dependency is not found. This happens before the
        graph command processes the tasks.
        """
        from doit.exceptions import InvalidTask
        output = StringIO()
        t1 = Task("t1", [""], task_dep=['nonexistent_task'])
        tasks = [t1]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['t1'])
        try:
            cmd_graph._execute(output='json')
            assert False, "Expected InvalidTask exception"
        except InvalidTask as e:
            assert 'nonexistent_task' in str(e)
            assert 'does not exist' in str(e)

    def test_circular_dependency(self):
        """Test that circular dependencies don't cause infinite loops.

        The BFS implementation uses a visited set, so circular dependencies
        should be handled gracefully.
        """
        output = StringIO()
        t1 = Task("t1", [""], task_dep=['t2'])
        t2 = Task("t2", [""], task_dep=['t3'])
        t3 = Task("t3", [""], task_dep=['t1'])
        tasks = [t1, t2, t3]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['t1'])
        result = cmd_graph._execute(output='json')

        assert result == 0
        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'t1', 't2', 't3'}

        t1_entry = next(e for e in data if e['name'] == 't1')
        assert t1_entry['task_dep'] == ['t2']

        t2_entry = next(e for e in data if e['name'] == 't2')
        assert t2_entry['task_dep'] == ['t3']

        t3_entry = next(e for e in data if e['name'] == 't3')
        assert t3_entry['task_dep'] == ['t1']

    def test_subtask_referenced_before_parent(self):
        """Test when a subtask is referenced directly before its parent.

        This tests the fallback path in _lazy_materialise where we search
        through pending subtasks by name rather than by parent basename.
        """
        output = StringIO()
        parent = Task("parent", None, has_subtask=True, task_dep=['parent:child'])
        child = Task("parent:child", [""], subtask_of='parent')
        t1 = Task("t1", [""], task_dep=['parent:child'])
        tasks = [parent, child, t1]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['t1'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}
        assert 'parent:child' in names
        assert 't1' in names

    def test_multiple_subtask_groups(self):
        """Test lazy materialization with multiple subtask groups.

        Ensure that materializing one group doesn't affect others.
        """
        output = StringIO()
        g1 = Task("g1", None, has_subtask=True, task_dep=['g1:a'])
        g1_a = Task("g1:a", [""], subtask_of='g1')
        g2 = Task("g2", None, has_subtask=True, task_dep=['g2:a'])
        g2_a = Task("g2:a", [""], subtask_of='g2')
        main = Task("main", [""], task_dep=['g1:a', 'g2:a'])
        tasks = [g1, g1_a, g2, g2_a, main]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['main'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'main', 'g1:a', 'g2:a'}

        assert 'g1' not in names
        assert 'g2' not in names

        main_entry = next(e for e in data if e['name'] == 'main')
        assert sorted(main_entry['task_dep']) == ['g1:a', 'g2:a']

    def test_deeply_nested_subtask_names(self):
        """Test subtask names with multiple colons (multi-level generators).

        doit supports multi-level generators which produce names like 'xpto:0-0'.
        The split(':', 1)[0] should correctly extract the basename.
        """
        output = StringIO()
        parent = Task("xpto", None, has_subtask=True, task_dep=['xpto:level1:level2'])
        nested = Task("xpto:level1:level2", [""], subtask_of='xpto')
        tasks = [parent, nested]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['xpto'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}
        assert names == {'xpto', 'xpto:level1:level2'}

    def test_setup_tasks_followed(self):
        """Test that setup tasks are followed in graph traversal."""
        output = StringIO()
        setup_task = Task("setup", [""])
        main_task = Task("main", [""], setup=['setup'])
        tasks = [setup_task, main_task]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['main'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'main', 'setup'}

        main_entry = next(e for e in data if e['name'] == 'main')
        assert main_entry['setup'] == ['setup']
        assert main_entry['task_dep'] == []

        setup_entry = next(e for e in data if e['name'] == 'setup')
        assert setup_entry['setup'] == []
        assert setup_entry['task_dep'] == []

    def test_empty_task_list(self):
        """Test behavior with empty task list."""
        output = StringIO()
        tasks = []

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks)
        result = cmd_graph._execute(output='json')

        assert result == 0
        data = json.loads(output.getvalue())
        assert data == []

    def test_calc_dep_not_traversed_but_displayed(self):
        """Test that calc_dep is displayed but not traversed.

        calc_dep is a calculated dependency resolved at runtime, so it
        shouldn't be followed during graph traversal, but should appear
        in the output.
        """
        output = StringIO()
        dep_task = Task("dep", [""])
        main_task = Task("main", [""], calc_dep=['dep'])
        tasks = [dep_task, main_task]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['main'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'main'}
        assert 'dep' not in names

        main_entry = next(e for e in data if e['name'] == 'main')
        assert main_entry['calc_dep'] == ['dep']
        assert main_entry['task_dep'] == []
        assert main_entry['setup'] == []

    def test_colon_in_task_name_not_a_subtask(self):
        """Test task with colon in name that is NOT a subtask.

        If a task name contains ':' but isn't a subtask, and there's
        a separate task group with a matching prefix, _lazy_materialise
        could incorrectly assume the colon indicates a subtask relationship.

        Example: 'build:release' (regular task) vs 'build' group with 'build:debug' subtask.
        """
        output = StringIO()
        build_release = Task("build:release", [""])

        build_group = Task("build", None, has_subtask=True, task_dep=['build:debug'])
        build_debug = Task("build:debug", [""], subtask_of='build')

        main = Task("main", [""], task_dep=['build:release'])

        tasks = [build_release, build_group, build_debug, main]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['main'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'main', 'build:release'}

        assert 'build' not in names
        assert 'build:debug' not in names

        main_entry = next(e for e in data if e['name'] == 'main')
        assert main_entry['task_dep'] == ['build:release']

    def test_subtask_name_doesnt_match_subtask_of_prefix(self):
        """Test subtask where name prefix doesn't match subtask_of value."""
        output = StringIO()
        real_parent = Task("real_parent", None, has_subtask=True, task_dep=['a:orphan'])
        orphan_subtask = Task("a:orphan", [""], subtask_of='real_parent')

        group_a = Task("a", None, has_subtask=True, task_dep=['a:normal'])
        normal_subtask = Task("a:normal", [""], subtask_of='a')

        main = Task("main", [""], task_dep=['a:orphan'])

        tasks = [real_parent, orphan_subtask, group_a, normal_subtask, main]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks, sel_tasks=['main'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'main', 'a:orphan'}

        assert 'a' not in names
        assert 'a:normal' not in names
        assert 'real_parent' not in names

        main_entry = next(e for e in data if e['name'] == 'main')
        assert main_entry['task_dep'] == ['a:orphan']

    def test_test_framework_naming_collision(self):
        """Realistic scenario: Test framework with naming collision.

        Simulates a multi-team codebase where:
        - Backend team has: api, api:build (subtask of 'api')
        - QA team has: smoke, api:smoke, web:smoke (subtasks of 'smoke')
        - CI depends on 'api:smoke' (QA's task, NOT backend's)
        """
        output = StringIO()

        api_group = Task("api", None, has_subtask=True, task_dep=['api:build'])
        api_build = Task("api:build", ["make build-api"], subtask_of='api')

        smoke_group = Task("smoke", None, has_subtask=True,
                           task_dep=['api:smoke', 'web:smoke'])
        api_smoke = Task("api:smoke", ["pytest tests/smoke/api"],
                         subtask_of='smoke')
        web_smoke = Task("web:smoke", ["pytest tests/smoke/web"],
                         subtask_of='smoke')

        ci_quick = Task("ci:quick", ["echo 'Quick CI passed'"],
                        task_dep=['api:smoke'])

        tasks = [api_group, api_build, smoke_group, api_smoke, web_smoke, ci_quick]

        cmd_graph = CmdFactory(Graph, outstream=output, task_list=tasks,
                               sel_tasks=['ci:quick'])
        cmd_graph._execute(output='json')

        data = json.loads(output.getvalue())
        names = {entry['name'] for entry in data}

        assert names == {'ci:quick', 'api:smoke'}

        assert 'api' not in names
        assert 'api:build' not in names
        assert 'smoke' not in names
        assert 'web:smoke' not in names

        ci_entry = next(e for e in data if e['name'] == 'ci:quick')
        assert ci_entry['task_dep'] == ['api:smoke']

        smoke_entry = next(e for e in data if e['name'] == 'api:smoke')
        assert smoke_entry['task_dep'] == []
        assert smoke_entry['setup'] == []
