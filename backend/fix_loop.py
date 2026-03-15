import sys

path = r"C:\Users\micha\Desktop\Project\BrandStorm\backend\routes\agent_loop.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
in_loop = False
for i, line in enumerate(lines):
    if "async for message in live_session.receive():" in line and not in_loop:
        out.append("        while True:\n")
        out.append("            async for message in live_session.receive():\n")
        in_loop = True
        continue
    
    if in_loop:
        if "logger.warning(f\"[{session.id}] Live API stream ended (receive generator exhausted)\")" in line:
            # This line and the one before should NOT be indented, as they are outside the while True loop.
            # wait, if the `while True` never ends on its own unless stream ends?
            # actually `while True` should end when `live_session.receive()` throws an exception,
            # or when the connection closes. If the generator is exhausted, it just loops again.
            # but if the websocket is closed, it raises an error.
            # So the lines:
            #         # If we reach here the Live API stream ended (server closed it)
            #         logger.warning(f"[{session.id}] Live API stream ended (receive generator exhausted)")
            # should remain as they were, because `while True` never naturally exits unless an exception is thrown,
            # or `break` is called.
            # Wait! If the server closes the connection, we get an exception instead of a silent exit!
            out.append("        # If we reach here the Live API stream ended (server closed it)\n")
            out.append(line)
            in_loop = False
        elif line.strip() == "":
            out.append(line)
        elif "If we reach here the Live API stream ended" in line:
            pass # skipping the original comment
        else:
            out.append("    " + line)
    else:
        out.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(out)
