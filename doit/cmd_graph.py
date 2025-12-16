"""command doit graph - inspect the task dependency graph"""

from collections import deque
import json

from .cmd_base import DoitCmdBase
from .control import TaskControl


opt_output_format = {
    'name': 'output',
    'short': '',
    'long': 'output',
    'type': str,
    'default': 'text',
    'choices': [
        ('text', 'human-readable output'),
        ('json', 'machine-readable JSON'),
    ],
    'help': ("choose output format when inspecting the task graph. "
             "[default: %(default)s]"),
}


class Graph(DoitCmdBase):
    """Inspect task relationships without executing actions."""

    doc_purpose = "inspect the task dependency graph"
    doc_usage = "[TASK ...]"
    doc_description = (
        "Display dependencies for the selected tasks without executing actions."
    )
    execute_tasks = True

    cmd_options = (opt_output_format,)

    def _execute(self, output='text', pos_args=None):
        control = TaskControl(self.task_list)
        control.process(self.sel_tasks)

        self._pending_lazy = self._prepare_lazy_materialisation(control)
        nodes = self._collect_nodes(control)
        graph_entries = self._describe_graph(control, nodes)

        if output == 'json':
            json.dump(graph_entries, self.outstream, indent=2)
            self.outstream.write('\n')
        else:
            self._print_text(graph_entries)
        return 0

    def _prepare_lazy_materialisation(self, control):
        """Strip generator-produced subtasks for lazy re-insertion later so they don't need to be processed again."""
        pending = {}
        for name, task in list(control.tasks.items()):
            if getattr(task, 'subtask_of', None):
                pending[name] = control.tasks.pop(name)
        return pending

    def _collect_nodes(self, control):
        """Return set of task names reachable from the selected tasks."""
        selected = control.selected_tasks or []
        visited = set()
        processed = set()
        queue = deque(selected)

        while queue:
            name = queue.popleft()
            visited.add(name)
            if name in visited:
                continue
            task = control.tasks.get(name)
            if task is None:
                self._lazy_materialise(control, name)
                if name in control.tasks:
                    queue.appendleft(name)
                visited.add(name)
                continue
            processed.add(name)
            queue.extend(dep for dep in task.task_dep if dep not in visited)
            queue.extend(dep for dep in task.setup_tasks if dep not in visited)
        return processed

    @staticmethod
    def _ordered_names(control, nodes):
        """Return deterministic order for printing nodes."""
        ordered = [name for name in control._def_order if name in nodes]
        if len(ordered) != len(nodes):
            remaining = nodes.difference(ordered)
            ordered.extend(sorted(remaining))
        return ordered

    def _describe_graph(self, control, nodes):
        """Build serialisable representation of the graph."""
        graph_entries = []
        for name in self._ordered_names(control, nodes):
            task = control.tasks[name]
            entry = {
                'name': name,
                'task_dep': sorted(task.task_dep),
                'setup': sorted(task.setup_tasks),
                'calc_dep': sorted(task.calc_dep),
            }
            graph_entries.append(entry)
        return graph_entries

    def _print_text(self, graph_entries):
        """Pretty print graph entries."""
        for entry in graph_entries:
            self.outstream.write(f"{entry['name']}\n")

            lines_printed = 0
            for label, key in (('task_dep', 'task_dep'),
                               ('setup', 'setup'),
                               ('calc_dep', 'calc_dep')):
                values = entry.get(key, [])
                if values:
                    deps = ', '.join(values)
                    self.outstream.write(f"  {label}: {deps}\n")
                    lines_printed += 1
            if lines_printed == 0:
                self.outstream.write("  (no dependencies)\n")
            self.outstream.write("\n")

    def _lazy_materialise(self, control, name):
        """Reinsert pending subtasks when first referenced by name."""
        pending = getattr(self, '_pending_lazy', {})
        if not pending:
            return

        basename = name.split(':', 1)[0]
        for candidate in list(pending.keys()):
            if candidate == name or candidate.startswith(f"{basename}:"):
                control.tasks[candidate] = pending.pop(candidate)

