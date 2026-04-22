import "./globals.css";

export const metadata = {
  title: "单票策略研究工作台",
  description: "面向 A 股单票研究的回测、实验与 AI 分析工作台。",
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
