import { StarIcon } from "./Icons";

interface Props {
  name: string;
  favorite: boolean;
  onToggle: () => void;
}

/** Star toggle for marking a company as a favorite. */
export default function FavoriteButton({ name, favorite, onToggle }: Props) {
  return (
    <button
      type="button"
      className={`watch-toggle ${favorite ? "on" : ""}`}
      title={favorite ? `Remove ${name} from favorites` : `Add ${name} to favorites`}
      aria-pressed={favorite}
      onClick={(e) => {
        e.stopPropagation();
        onToggle();
      }}
    >
      <StarIcon filled={favorite} />
      Favorite
    </button>
  );
}
