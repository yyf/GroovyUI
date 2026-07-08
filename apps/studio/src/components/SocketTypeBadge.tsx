import { socketTypeClass } from "../socketTypes";

type Props = {
  type: string;
  title?: string;
};

export default function SocketTypeBadge({ type, title }: Props) {
  return (
    <span className={`socket-type-badge ${socketTypeClass(type)}`} title={title ?? type}>
      {type}
    </span>
  );
}
