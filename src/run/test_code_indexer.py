from code_indexer.workspace_indexer import scan_workspace
from code_indexer.code_search import search_code


workspace = scan_workspace("workspace")

print("Functions:")
for f in workspace.functions:
    print(f)

print("\nCall Graph:")
print(workspace.call_graph)


print("\nSemantic Search:")
results = search_code("add numbers")

for r in results:
    print(r["function"])