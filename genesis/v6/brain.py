import os
import json
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parents[2] / "runtime" / "v6_brain_weights.npz"

class ContinuousBrain:
    def __init__(self, input_dim: int = 512, hidden_dim: int = 128, output_dim: int = 101, weights_path: Path = DEFAULT_WEIGHTS_PATH):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.weights_path = weights_path
        
        # Xavier Normal Initialization
        np.random.seed(42)
        self.W1 = np.random.randn(input_dim, hidden_dim) * np.sqrt(2.0 / (input_dim + hidden_dim))
        self.b1 = np.zeros((1, hidden_dim), dtype=np.float32)
        self.W2 = np.random.randn(hidden_dim, output_dim) * np.sqrt(2.0 / (hidden_dim + output_dim))
        self.b2 = np.zeros((1, output_dim), dtype=np.float32)
        
        # 内部缓存，用于反向传播
        self._cache_X: Optional[np.ndarray] = None
        self._cache_Z1: Optional[np.ndarray] = None
        self._cache_A1: Optional[np.ndarray] = None
        self._cache_A2: Optional[np.ndarray] = None

    def forward(self, X: np.ndarray) -> np.ndarray:
        """
        前向传播计算概率。
        X.shape = (N, 512)
        Returns:
            A2.shape = (N, V) 激活后的多标签概率分布
        """
        self._cache_X = X
        
        # Hidden Layer: Z1 = X * W1 + b1, A1 = ReLU(Z1)
        self._cache_Z1 = np.dot(X, self.W1) + self.b1
        self._cache_A1 = np.maximum(0, self._cache_Z1)
        
        # Output Layer: Z2 = A1 * W2 + b2, A2 = Sigmoid(Z2)
        Z2 = np.dot(self._cache_A1, self.W2) + self.b2
        self._cache_A2 = 1.0 / (1.0 + np.exp(-np.clip(Z2, -20, 20)))  # clip 防止溢出
        
        return self._cache_A2

    def backward(self, Y: np.ndarray, lr: float = 0.01, lambda_decay: float = 0.001) -> float:
        """
        反向传播梯度并执行带有 L2 衰减 (Weight Decay) 的 SGD 更新。
        Y.shape = (N, V) 真实的多标签二元向量
        """
        if self._cache_X is None or self._cache_A2 is None:
            raise RuntimeError("Must run forward before backward")
            
        N = Y.shape[0]
        
        # 计算 BCE Loss
        A2 = self._cache_A2
        epsilon = 1e-15
        loss = -np.mean(Y * np.log(A2 + epsilon) + (1.0 - Y) * np.log(1.0 - A2 + epsilon))
        # 加上 L2 正则化
        loss += 0.5 * lambda_decay * (np.sum(self.W1 ** 2) + np.sum(self.W2 ** 2))
        
        # Output Layer Gradients
        dZ2 = (A2 - Y) / N
        dW2 = np.dot(self._cache_A1.T, dZ2) + lambda_decay * self.W2
        db2 = np.sum(dZ2, axis=0, keepdims=True)
        
        # Hidden Layer Gradients
        dA1 = np.dot(dZ2, self.W2.T)
        dZ1 = dA1 * (self._cache_Z1 > 0)  # ReLU 导数
        dW1 = np.dot(self._cache_X.T, dZ1) + lambda_decay * self.W1
        db1 = np.sum(dZ1, axis=0, keepdims=True)
        
        # 更新权重 (SGD with Weight Decay)
        self.W1 -= lr * dW1
        self.b1 -= lr * db1
        self.W2 -= lr * dW2
        self.b2 -= lr * db2
        
        return float(loss)

    def save_weights(self) -> None:
        """将权重和偏差保存到本地 .npz"""
        self.weights_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            self.weights_path,
            W1=self.W1,
            b1=self.b1,
            W2=self.W2,
            b2=self.b2,
            dims=np.array([self.input_dim, self.hidden_dim, self.output_dim])
        )

    def load_weights(self) -> bool:
        """从本地加载权重。成功返回 True，文件不存在或维度冲突返回 False"""
        if not self.weights_path.exists():
            return False
        try:
            data = np.load(self.weights_path)
            # 校验维度
            if "dims" in data:
                dims = data["dims"]
                if len(dims) == 3 and (dims[0] != self.input_dim or dims[2] != self.output_dim):
                    return False
            self.W1 = data["W1"]
            self.b1 = data["b1"]
            self.W2 = data["W2"]
            self.b2 = data["b2"]
            return True
        except Exception:
            return False

    def fit(self, X: np.ndarray, Y: np.ndarray, epochs: int = 100, lr: float = 0.05, lambda_decay: float = 0.001, verbose: bool = True) -> list:
        """模型训练循环"""
        losses = []
        for epoch in range(1, epochs + 1):
            preds = self.forward(X)
            loss = self.backward(Y, lr, lambda_decay)
            losses.append(loss)
            if verbose and (epoch == 1 or epoch % 10 == 0 or epoch == epochs):
                print(f"Epoch {epoch}/{epochs} - Loss: {loss:.6f}")
        return losses
