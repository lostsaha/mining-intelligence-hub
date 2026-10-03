"""验证智谱 embedding-3 可用性与维度。"""
import sys

sys.path.insert(0, r"E:\syn\矿业聚合平台\backend")

from app import emb  # noqa: E402

print("EMBEDDINGS_ENABLED:", emb.EMBEDDINGS_ENABLED, "| model:", emb.EMBEDDINGS_MODEL)
vecs = emb.embed(["露天矿边坡稳定监测", "mine slope stability monitoring"])
print("维度:", len(vecs[0]), "| 两条向量是否不同:", vecs[0][:3] != vecs[1][:3])
print("样例前5维:", [round(x, 4) for x in vecs[0][:5]])
