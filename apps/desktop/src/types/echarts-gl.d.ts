declare module "echarts-gl";

declare module "echarts-gl/lib/util/graphicGL" {
  interface ShaderStatic {
    import(source: string): void;
    source(name: string): string | undefined;
  }
  const graphicGL: { Shader: ShaderStatic };
  export default graphicGL;
}

declare module "echarts-gl/lib/util/geometry/Bars3DGeometry" {
  const BarsGeometry: {
    prototype: Record<string, unknown>;
  };
  export default BarsGeometry;
}
