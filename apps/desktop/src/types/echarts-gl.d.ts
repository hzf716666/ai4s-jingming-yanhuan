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

declare module "echarts-gl/lib/util/shader/lines3D.glsl.js" {
  const shaderSource: string;
  export default shaderSource;
}
