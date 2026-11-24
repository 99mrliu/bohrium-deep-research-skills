<?xml version="1.0" encoding="UTF-8"?>
<map version="1.0.1">
  <node TEXT="催化剂Q研究规划" ID="root">
    <node TEXT="应用验证" ID="n-app">
      <node TEXT="CO2加氢性能评价" ID="n-app-1"/>
    </node>
    <node TEXT="表征方案" ID="n-char">
      <node TEXT="XRD与SEM（联用）" ID="n-char-1">
        <arrowlink DESTINATION="n-app-1"/>
      </node>
      <node TEXT="原位红外测试" ID="n-char-2"/>
    </node>
    <node TEXT="文献调研" ID="n-lit">
      <node TEXT="文献计量分析" ID="n-lit-1">
        <rich_content TYPE="NOTE"><html><head/><body><p>检索式示例："catalyst &amp; Q"（合成示例数据，仅演示 XML 转义）。</p></body></html></rich_content>
      </node>
      <node TEXT="关键催化剂体系梳理" ID="n-lit-2">
        <arrowlink DESTINATION="n-syn-2"/>
      </node>
    </node>
    <node TEXT="合成路线" ID="n-syn">
      <node TEXT="水热合成参数优化" ID="n-syn-1">
        <rich_content TYPE="NOTE"><html><head/><body><p>重点关注温度与保温时间的交互作用；参数范围参考既往水热法经验。</p></body></html></rich_content>
        <node TEXT="温度梯度实验" ID="n-syn-1a">
          <arrowlink DESTINATION="n-syn-1b"/>
        </node>
        <node TEXT="前驱体比例筛选" ID="n-syn-1b"/>
      </node>
      <node TEXT="掺杂策略筛选" ID="n-syn-2"/>
    </node>
  </node>
</map>
