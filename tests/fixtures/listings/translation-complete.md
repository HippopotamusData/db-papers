**清单 1：向量化哈希表探测循环。**

```cpp
for (auto tuple : input) {
    if (tuple.key == key) {
        return tuple.value;
    }
}
```
