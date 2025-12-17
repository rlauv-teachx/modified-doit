"""command doit graph - inspect the task dependency graph"""

from collections import deque, defaultdict
from itertools import chain
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

    DEPENDENCY_TYPES = [
        ('task_dep', 'task_dep'),
        ('setup', 'setup'),
        ('calc_dep', 'calc_dep'),
    ]

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
        """Strip generator-produced subtasks for lazy re-insertion later.
        
        Subtasks are removed from control.tasks and stored in a pending dict
        keyed by their parent task name, so they can be materialized on-demand
        when first referenced.
        """
        pending = defaultdict(dict)
        for name, task in list(control.tasks.items()):
            if getattr(task, 'subtask_of', None):
                control.tasks.pop(name)
                pending[task.subtask_of][name] = task
        return pending

    def _collect_nodes(self, control):
        """Return set of task names reachable from the selected tasks.
        
        Performs a breadth-first search starting from selected tasks,
        following task_dep and setup_tasks dependencies and materializing
        subtasks on-demand.
        """
        selected = control.selected_tasks or []
        visited = set()
        processed = set()
        queue = deque(selected)

        while queue:
            name = queue.popleft()
            if name in visited:
                continue

            visited.add(name)
            task = control.tasks.get(name)
            if task is None:
                self._lazy_materialise(control, name)
                task = control.tasks.get(name)

            if task is None:
                continue

            processed.add(name)
            for dep in self._get_all_dependencies(task):
                if dep not in visited:
                    queue.append(dep)
        return processed

    @staticmethod
    def _get_all_dependencies(task):
        """Return all dependencies for a task.
        
        Returns an iterator over all dependencies without creating
        intermediate lists for better memory efficiency.
        """
        return chain(task.task_dep, task.setup_tasks)

    @staticmethod
    def _ordered_names(control, nodes):
        """Return deterministic order for printing nodes.
        
        Tasks are ordered by their definition order, with any remaining
        nodes (not in definition order) appended in sorted order.
        """
        ordered = [name for name in control._def_order if name in nodes]
        remaining = nodes - set(ordered)
        if remaining:
            ordered.extend(sorted(remaining))
        return ordered

    def _describe_graph(self, control, nodes):
        """Build serialisable representation of the graph."""
        graph_entries = []
        for name in self._ordered_names(control, nodes):
            task = control.tasks.get(name)
            if task is None:
                continue
            entry = {
                'name': name,
                'task_dep': sorted(task.task_dep),
                'setup': sorted(task.setup_tasks),
                'calc_dep': sorted(task.calc_dep),
            }
            graph_entries.append(entry)
        return graph_entries

    def _print_text(self, graph_entries):
        """Pretty print graph entries in human-readable format."""
        for entry in graph_entries:
            self.outstream.write(f"{entry['name']}\n")

            has_dependencies = False
            for label, key in self.DEPENDENCY_TYPES:
                values = entry.get(key, [])
                if values:
                    deps = ', '.join(values)
                    self.outstream.write(f"  {label}: {deps}\n")
                    has_dependencies = True

            if not has_dependencies:
                self.outstream.write("  (no dependencies)\n")
            self.outstream.write("\n")

    def _lazy_materialise(self, control, name):
        """Reinsert pending subtasks when first referenced by name.
        
        When a task name is referenced, this method checks if there are
        pending subtasks that should be materialized. It tries two approaches:
        1. If the name contains ':', extract basename (e.g., 'g1:a' -> 'g1')
        2. Check if the name appears as a subtask in any pending group
        """
        pending = self._pending_lazy
        if not pending:
            return

        basename = name.split(':', 1)[0]
        if basename in pending:
            control.tasks.update(pending.pop(basename))
            return

        for group, tasks in pending.items():
            if basename in tasks:
                control.tasks.update(tasks)
                return
