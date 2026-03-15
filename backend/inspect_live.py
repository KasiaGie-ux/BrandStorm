import inspect
import typing
from google.genai import types

print("--- LiveConnectConfig ---")
for f, info in types.LiveConnectConfig.model_fields.items():
    print(f, getattr(info, "annotation", ""))

print("\n--- AutomaticActivityDetection ---")
for f, info in types.AutomaticActivityDetection.model_fields.items():
    print(f, getattr(info, "annotation", ""))

print("\n--- BidiGenerateContentClientContent ---")
for f, info in types.BidiGenerateContentClientContent.model_fields.items():
    print(f, getattr(info, "annotation", ""))

print("\n--- BidiGenerateContentRealtimeInput ---")
for f, info in set(getattr(types, "BidiGenerateContentRealtimeInput", type("Dummy",(),{"model_fields":{}})).model_fields.items()):
    print(f, getattr(info, "annotation", ""))

import google.genai.live as g_live
print("\n--- Live Module Dir ---")
print(dir(g_live))
