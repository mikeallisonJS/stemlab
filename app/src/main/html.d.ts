// esbuild inlines .html imports as strings (--loader:.html=text)
declare module "*.html" {
  const content: string;
  export default content;
}
