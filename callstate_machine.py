from enum import Enum, auto
import threading
import logging

class CallState(Enum):
		IDLE = auto()         # 대기중
		TRYING = auto()       # 시도중
		IN_CALL = auto()      # 통화중
		TERMINATED = auto()   # 통화종료

class CallStateMachine:
		def __init__(self):
				self.state = CallState.IDLE
				self._lock = threading.Lock()
				self._logger = logging.getLogger(__name__)

		def update_state(self, new_state):
				with self._lock:
						if self.is_valid_transition(new_state):
								self._logger.info(f"상태 전이: {self.state.name} -> {new_state.name}")
								self.state = new_state
						else:
								self._logger.warning(f"잘못된 상태 전이 시도: {self.state.name} -> {new_state.name}")

		def is_valid_transition(self, new_state):
				valid_transitions = {
						CallState.IDLE: [CallState.TRYING],
						CallState.TRYING: [CallState.IN_CALL, CallState.TERMINATED],
						CallState.IN_CALL: [CallState.TERMINATED],
						CallState.TERMINATED: [CallState.IDLE]
				}
				return new_state in valid_transitions.get(self.state, [])