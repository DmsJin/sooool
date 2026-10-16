"""Public actor observation projection, shared by native evaluation."""
def observation_context(frames,snapshot,*,request_version,memory="",rtt_history_ms=()):
 return {"frames":frames,"external_now_ms":snapshot["clock_ms"],"pending_plans":snapshot.get("pending",[]),"executed_acks":snapshot.get("rawacks",[]),"rtt_history_ms":list(rtt_history_ms),"model_memory":memory,"request_version":request_version,"queue_version":snapshot.get("version",snapshot.get("queue_version",0))}
