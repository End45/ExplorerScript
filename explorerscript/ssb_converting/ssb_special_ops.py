"""
Registry of special known ssb operations for the decompiler and some code to handle them.
ExplorerScript only maps ssb opcodes by name.
TODO: These are only valid for Sky-style ssb.
"""
#  MIT License
#
#  Copyright (c) 2020 Parakoopa
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#
from typing import Dict, Union, List, Optional

from igraph import Graph, Vertex

from explorerscript.ssb_converting.ssb_data_types import SsbOperation, SsbOpCode, SsbOpParamConstant

OP_JUMP = 'Jump'

OPS_BRANCH = {
    'Branch': 2,
    'BranchBit': 2,
    'BranchDebug': 1,
    'BranchEdit': 1,
    'BranchExecuteSub': 1,
    'BranchPerformance': 2,
    'BranchScenarioNow': 3,
    'BranchScenarioNowAfter': 3,
    'BranchScenarioNowBefore': 3,
    'BranchScenarioAfter': 3,
    'BranchScenarioBefore': 3,
    'BranchSum': 3,
    'BranchValue': 3,
    'BranchVariable': 3,
    'BranchVariation': 1,
}

OPS_SWITCH_CASE_MAP = {
    'message_SwitchMenu': ['CaseMenu', 'CaseMenu2'],
    'message_SwitchMenu2': ['CaseMenu', 'CaseMenu2'],
    'Switch': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'SwitchSector': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'ProcessSpecial': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'message_Menu': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'SwitchScenario': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'SwitchRandom': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'SwitchScenarioLevel': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario'],
    'SwitchDungeonMode': ['Case', 'CaseValue', 'CaseVariable', 'CaseScenario']
}

# TODO!!!
OPS_SWITCH_TEXT_CASE_MAP = {
    'message_SwitchTalk': ['CaseText', 'DefaultText'],
    'message_SwitchMonologue': ['CaseText', 'DefaultText'],
}

# A list of ops with jumps to memory offsets, values are the parameter index containing the jump
OPS_WITH_JUMP_TO_MEM_OFFSET = {
    #'Call': 0,  TODO: Check
    #'CancelRecoverCommon': 0,  TODO: Check
    'Case': 1,
    'CaseMenu': 1,
    'CaseMenu2': 1,
    'CaseScenario': 2,
    'CaseValue': 2,
    'CaseVariable': 2,
    # Special case; this OpCode ALWAYS jumps:
    OP_JUMP: 0,
}
OPS_WITH_JUMP_TO_MEM_OFFSET.update(OPS_BRANCH)


# THEORY:
# Hold doesn't ACTUALLY end the execution, it just freezes the calling object/"thread" forever,
# until the script is replaced?
# After Hold we can assume the execution flow is stopped, but sometimes there's also still another token of
# OPS_THAT_END_CONTROL_FLOW after it, and we should probably include that when reading in ssb.
# TODO: in some cases Hold might actually be able to continue and also be used that way!
OP_HOLD = 'Hold'
OP_RETURN = 'Return'
OP_END = 'End'

# These ops end the control flow in the current routine
# (usually by jumping somewhere else and NOT "automatically" returining.)
# This does not include OpCodes that MAY jump somewhere else (branching opcodes, see above)
OPS_THAT_END_CONTROL_FLOW = [
    OP_JUMP, OP_RETURN, OP_END, OP_HOLD, 'JumpCommon', 'Destroy'
]


OPS_CTX_LIVES = 'lives'
OPS_CTX_OBJECT = 'object'
OPS_CTX_PERFORMER = 'performer'
# The next OP after these will be executed in the context of an actor/object/performer
OPS_CTX = [OPS_CTX_LIVES, OPS_CTX_OBJECT, OPS_CTX_PERFORMER]


class LabelMarker:
    pass


class LabelJumpMarker:
    pass


class IfStart(LabelJumpMarker):
    def __init__(self, if_id: int):
        self.if_id = if_id
        self.is_not = False

    def __str__(self):
        return f"IF{' NOT' if self.is_not else ''}({self.if_id})"


class MultiIfStart(IfStart):
    def __init__(self, if_id: int, start_ifs, ifs_are_not):
        super().__init__(if_id)
        self.original_ssb_ifs_ops: List[SsbOperation] = start_ifs
        self.original_ssb_ifs_is_not: List[bool] = ifs_are_not

    def __str__(self):
        return f"MIF({self.if_id}[{len(self.original_ssb_ifs_ops)}])"

    def add_if(self, ssb_if: SsbOperation, is_not: bool):
        """Add the ORIGINAL opcodes (NOT SsbLabelJump, but their ROOT) to this list of ifs."""
        self.original_ssb_ifs_ops.append(ssb_if)
        self.original_ssb_ifs_is_not.append(is_not)


class SwitchStart(LabelJumpMarker):
    def __init__(self, switch_id: int):
        self.switch_id = switch_id

    def __str__(self):
        return f"SWITCH({self.switch_id})"


class MultiSwitchStart(SwitchStart):
    def __init__(self, if_id: int, start_switches):
        super().__init__(if_id)
        self.original_ssb_switch_ops: List[SsbOperation] = start_switches

    def __str__(self):
        return f"MSWITCH({self.switch_id})"

    def add_switch(self, ssb_switch: SsbOperation):
        """Add the ORIGINAL opcodes (NOT SsbLabelJump, but their ROOT) to this list of switches."""
        self.original_ssb_switch_ops.append(ssb_switch)

    def number_of_switches(self):
        return len(self.original_ssb_switch_ops)


class ForeverContinue(LabelJumpMarker):
    def __init__(self, loop_id: int):
        self.loop_id = loop_id

    def __str__(self):
        return f"LOOP_CONTINUE({self.loop_id})"


class ForeverBreak(LabelJumpMarker):
    def __init__(self, loop_id: int):
        self.loop_id = loop_id

    def __str__(self):
        return f"LOOP_BREAK({self.loop_id})"


class IfEnd(LabelMarker):
    def __init__(self, if_id: int):
        self.if_id = if_id

    def __str__(self):
        return f"IF({self.if_id})"


class SwitchEnd(LabelMarker):
    def __init__(self, switch_id: int):
        self.switch_id = switch_id

    def __str__(self):
        return f"SWITCH({self.switch_id})"


class SwitchFalltrough(LabelMarker):
    def __str__(self):
        return f"FALL"


class ForeverStart(LabelMarker):
    def __init__(self, loop_id: int):
        self.loop_id = loop_id

    def __str__(self):
        return f"LOOP({self.loop_id})"


class ForeverEnd(LabelMarker):
    def __init__(self, loop_id: int):
        self.loop_id = loop_id

    def __str__(self):
        return f"END_LOOP({self.loop_id})"


class SsbLabel(SsbOperation):
    """A label that other operations can jump to"""
    def __init__(self, id: int, routine_id: int):
        #                                                      Params only for debugging
        super().__init__(-1, SsbOpCode(-1, f'ES_LABEL<{id}>'), [id])
        self.id: int = id
        # Routine id this label lies in
        self.routine_id = routine_id
        # Whether or not this label is referenced from another routine
        self.referenced_from_other_routine = False
        # Markers for this label (type of label)
        self.markers: List[LabelMarker] = []

    def add_marker(self, m: LabelMarker):
        self.markers.append(m)

    def needs_to_be_printed(self, number_in_vs: int, graph: Graph):
        """If the number of incoming vertices is bigger than max_in_vs, then we need to print this label"""
        max_in_vs = 1
        for m in self.markers:
            if isinstance(m, IfEnd):
                max_in_vs += 1  # Each if adds one else branch.
            if isinstance(m, SwitchEnd):
                start: Vertex = self._find_switch_start_vertex(graph, m.switch_id)
                if not start:
                    raise ValueError(f"Start for switch {m.switch_id} not found.")
                max_in_vs += len(start.out_edges()) - 1
        return number_in_vs > max_in_vs

    @staticmethod
    def _find_switch_start_vertex(graph: Graph, switch_id: int) -> Optional[Vertex]:
        for v in graph.vs:
            if 'op' not in v.attributes():
                continue
            if isinstance(v['op'], SsbLabelJump):
                for m in v['op'].markers:
                    if isinstance(m, SwitchStart) and m.switch_id == switch_id:
                        return v
        return None


class SsbForeignLabel(SsbOperation):
    """A reference to a label in another routine"""
    def __init__(self, label: SsbLabel):
        #                                                              Params only for debugging
        super().__init__(-1, SsbOpCode(-1, f'ES_FOREIGN<{label.id}>'), [label.id])
        self.label = label


class SsbLabelJump(SsbOperation):
    """An op that jumps to a label."""
    def __init__(self, root: SsbOperation, label: Union[SsbLabel, None]):
        if label is not None:
            label_id = label.id
        else:
            label_id = -1
        #                                                                             Params only for debugging
        super().__init__(root.offset, SsbOpCode(-1, f'ES_JUMP<{root.op_code.name}>'), [label_id])
        self.root = root
        # May be None, if so the connected edges determine the different jumps
        self.label = label
        # Markers for this jump (type of jump)
        self.markers: List[LabelJumpMarker] = []

    def add_marker(self, m: LabelJumpMarker):
        if len(self.markers) > 0:
            raise ValueError("Jumps can currently only have one or zero markers.")
        self.markers.append(m)

    def remove_marker(self):
        """Remove the first (and only) marker if exists."""
        if len(self.markers) > 0:
            del self.markers[0]

    def get_marker(self):
        """Returns the first (and only) marker if exists, otherwise None."""
        if len(self.markers) > 0:
            return self.markers[0]
        return None


class SwitchCaseOperation:
    """ For marking the edge of a switch. """
    def __init__(self, switch_index: int, index: int, op: SsbOperation):
        self.switch_index = switch_index
        self.index = index
        self.op = op

    def __str__(self):
        return f"{self.switch_index}:{self.index} :: {self.op}"


def process_op_for_jump(op: SsbOperation, known_labels: Dict[int, SsbLabel], routine_id: int) -> SsbOperation:
    """
    Processes the operation.
    If it doesn't contain a jump to a memory offset, op is simply returned.

    Otherwise, a label for the jump location is searched in known_labels.
    - If found: Returns a OperationSubtree with a copy of op as root, and the label op as subtree.
                The param with the jump offset is removed from the op copy.
    - If not found: A new label with an auto-incremented id is generated and added to the known_labels.
                    Then: see above for "if found".
    """
    if op.op_code.name in OPS_WITH_JUMP_TO_MEM_OFFSET.keys():
        param_list = op.params if isinstance(op.params, list) else list(op.params.values())
        jump_param_idx = OPS_WITH_JUMP_TO_MEM_OFFSET[op.op_code.name]
        if len(param_list) < jump_param_idx:
            raise ValueError(f"The parameters for the OpCode {op.op_code.name} must contain a jump address at index {jump_param_idx}.")
        old_offset = param_list[jump_param_idx]
        if old_offset in known_labels:
            label = known_labels[old_offset]
            if routine_id != label.routine_id:
                label.referenced_from_other_routine = True
        else:
            if len(known_labels) == 0:
                next_label_id = 0
            else:
                next_label_id = max(label.id for label in known_labels.values()) + 1
            label = SsbLabel(next_label_id, routine_id)
            known_labels[old_offset] = label
        new_params = param_list.copy()
        del new_params[jump_param_idx]
        return SsbLabelJump(
            SsbOperation(op.offset, op.op_code, new_params),
            label
        )
    return op
