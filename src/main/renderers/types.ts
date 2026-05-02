/**
 * Generic spec types for the screen renderer.
 *
 * The agent receives a wireframe (and optionally a PRD.md) and authors a
 * `ScreenSpec` — a list of `SectionSpec` instances. The renderer compiles
 * the spec into figma plugin JS that produces polished output deterministically.
 *
 * The agent NEVER touches figma abstractions (frame, autoLayout, fillVar, etc.)
 * — it only picks component types and fills data.
 */

export type ColorHue = 'purple' | 'pink' | 'amber' | 'green' | 'blue' | 'red';

export type IconKey =
  | 'bell' | 'message' | 'home' | 'shoppingBag' | 'award'
  | 'users' | 'menu' | 'wallet' | 'plus' | 'minus' | 'gift'
  | 'star' | 'starFilled'
  | 'currencyDollarCircle' | 'creditCard' | 'diamond'
  | 'xClose' | 'xCircle' | 'chevronLeft' | 'chevronRight'
  | 'check' | 'checkCircle' | 'infoCircle' | 'sparkle'
  | 'eye' | 'search';

// ─── Section types ────────────────────────────────────────────────────────

export interface AppHeaderSection {
  type: 'appHeader';
  /** Right-side icon button list. Default: ['bell', 'message']. */
  rightIcons?: IconKey[];
  /** Override the in-file Logo with custom text. */
  logoText?: string;
}

export interface ModalHeaderSection {
  type: 'modalHeader';
  /** Optional title centered between the close X and the leading slot. */
  title?: string;
  showClose?: boolean; // default true
}

export interface BackHeaderSection {
  type: 'backHeader';
  title?: string;
}

export interface FilterChipRowSection {
  type: 'filterChipRow';
  chips: Array<{ text: string; selected?: boolean }>;
}

export interface SegmentedTabSection {
  type: 'segmentedTab';
  tabs: Array<{ id: string; label: string }>;
  activeId: string;
}

export interface UnderlineTabSection {
  type: 'underlineTab';
  tabs: Array<{ id: string; label: string }>;
  activeId: string;
}

export interface SectionHeaderRow {
  type: 'sectionHeader';
  title: string;
  /** Trailing text or "전체보기(N)" link. */
  trailing?: string;
}

export interface StepperCardSection {
  type: 'stepperCard';
  rows: Array<{ label: string; value: string; unit: string }>;
}

export interface MakerSpec {
  name: string;
  level: string;
  colorHue: ColorHue;
  crown?: boolean;
}

export interface AvatarRowSection {
  type: 'avatarRow';
  add?: { label: string };
  makers: MakerSpec[];
}

export interface SummaryCardLinkRowsSection {
  type: 'summaryCardLinkRows';
  title: string;
  /** Right-side icons next to the title (e.g. check + sparkle). */
  titleIcons?: IconKey[];
  rows: Array<{
    label: string;
    value: string;
    /** Visual tone for the value text. */
    valueTone?: 'positive' | 'negative' | 'neutral';
    /** Render value as an underlined link (default: false). */
    asLink?: boolean;
  }>;
}

export interface MonthScrollerCalendarSection {
  type: 'monthScrollerCalendar';
  /** Header centered above the strip. */
  title?: string;
  months: Array<{
    short: string;       // "Jan"
    day: string;         // "1"
    active?: boolean;
    activeLabel?: string; // "이번달"
    badge?: boolean;     // small dot indicator
  }>;
  filterLabel?: string;  // e.g. "납입 ▼"
}

export interface StatsStrip3ColSection {
  type: 'statsStrip3Col';
  cols: Array<{ label: string; value: string; valueTone?: 'positive' | 'negative' | 'neutral' }>;
}

export type TransactionRowState =
  | 'overdue'   // D+n, 미납 — red badge + outline pill
  | 'today'    // D-day, 오늘 — brand badge
  | 'soon'     // D-1, 임박 — brand badge
  | 'scheduled' // D-n, 예정 — neutral badge + outline pill
  | 'completed'; // 완료 — success badge + text label

export interface TransactionTimelineSection {
  type: 'transactionTimeline';
  items: Array<{
    /** "29일", "1일", "10일" */
    dayLabel: string;
    /** "D+3", "오늘", "D-1", "D-10" */
    dayState: string;
    /** Drives badge background + title color + right action style. */
    rowState: TransactionRowState;
    /** "미납 (1/5회차)", "납입 (1/5회차)" */
    title: string;
    amount: string;
    /** "납입 하기", "선납 하기", "납입 처리 완료", "납입 완료" */
    rightAction: string;
    /**
     * Progress 0..100. If omitted, the renderer auto-extracts from the
     * "(N/M회차)" pattern inside title.
     */
    progressPercent?: number;
  }>;
}

export interface StageItem {
  monthly: number;
  months: number;
  payoutAt: number;
  payout: number;
  interest: number;
  points: number;
  fee: number;
}

export interface StageCardListSection {
  type: 'stageCardList';
  layout: 'timeline';
  items: StageItem[];
}

export interface FooterLegalSection {
  type: 'footerLegal';
  legalLinks: string[];
  companyName: string;
  bizNumber: string;
  ceo: string;
  teleSalesNumber: string;
  disclaimer: string;
  copyright: string;
}

export interface TabBarSection {
  type: 'tabBar';
  tabs: Array<{ id: string; label: string; iconKey: IconKey }>;
  activeId: string;
}

export interface FabSection {
  type: 'fab';
  iconKey: IconKey;
}

export interface SpacerSection {
  type: 'spacer';
  height: number;
}

// ─── Phase 1 additions ──────────────────────────────────────────────────

export type AlertTone = 'error' | 'warning' | 'info' | 'success';

export interface AlertBannerSection {
  type: 'alertBanner';
  tone: AlertTone;
  iconKey?: IconKey;
  title: string;
  description?: string;
  trailingChevron?: boolean;
}

export interface RecommendHeroSection {
  type: 'recommendHero';
  topLabel: string;
  amount: string;
  unit: string;
  subText?: string;
  slider?: { label: string; valueText: string; current: number; max: number };
  steppers?: Array<{ label: string; value: string; unit?: string }>;
  ctaText: string;
  toggleText?: string;
}

export type StageCardStatus = 'inProgress' | 'scheduled' | 'overdue' | 'completed';

export interface StageCardScrollSection {
  type: 'stageCardScroll';
  cards: Array<{
    status: StageCardStatus;
    statusLabel: string;
    rate: string;
    amount: string;
    description?: string;
    favorited?: boolean;
  }>;
}

export interface CreditUsageCardSection {
  type: 'creditUsageCard';
  usageLabel: string;
  usageAmount: string;
  usageUnit: string;
  rightInfo: string;
  progressPercent?: number;
  cta?: { iconKey?: IconKey; text: string; tone?: 'info' | 'warning' };
}

// ─── Phase 2 additions ──────────────────────────────────────────────────

export type AttendanceDayState = 'completed' | 'today' | 'future';

export interface AttendanceWeekSection {
  type: 'attendanceWeek';
  streakText: string;
  rewardText: string;
  ctaText: string;
  days: Array<{ label: string; state: AttendanceDayState }>;
}

export interface EventBannerCarouselSection {
  type: 'eventBannerCarousel';
  banners: Array<{
    badge?: string;
    title: string;
    description?: string;
    iconKey?: IconKey;
    tone?: 'brand' | 'neutral';
  }>;
  activeIndex?: number;
}

export type NotificationKind = 'transaction' | 'event' | 'system';

export interface NotificationListSection {
  type: 'notificationList';
  items: Array<{
    kind: NotificationKind;
    title: string;
    body: string;
    time: string;
    unread?: boolean;
  }>;
}

export interface ParagraphSection {
  type: 'paragraph';
  text: string;
  align?: 'left' | 'center' | 'right';
  weight?: 'regular' | 'medium' | 'bold';
  size?: 11 | 12 | 13 | 14 | 16;
  tone?: 'primary' | 'secondary' | 'tertiary' | 'brandPrimary' | 'errorPrimary';
  underline?: boolean;
}

export type ProductBadgeKind = 'hotdeal' | 'best' | 'new';

export interface ProductHotDealSection {
  type: 'productHotDeal';
  title: string;
  pointBalance: string;
  trailing?: string;
  products: Array<{
    badge?: ProductBadgeKind;
    name: string;
    discount?: string;
    price: string;
    imageHue?: ColorHue;
  }>;
}

export type SectionSpec =
  | AppHeaderSection
  | ModalHeaderSection
  | BackHeaderSection
  | FilterChipRowSection
  | SegmentedTabSection
  | UnderlineTabSection
  | SectionHeaderRow
  | StepperCardSection
  | AvatarRowSection
  | SummaryCardLinkRowsSection
  | MonthScrollerCalendarSection
  | StatsStrip3ColSection
  | TransactionTimelineSection
  | StageCardListSection
  | FooterLegalSection
  | SpacerSection
  | AlertBannerSection
  | RecommendHeroSection
  | StageCardScrollSection
  | CreditUsageCardSection
  | AttendanceWeekSection
  | EventBannerCarouselSection
  | ProductHotDealSection
  | ParagraphSection
  | NotificationListSection;

export type OverlaySpec = TabBarSection | FabSection;

export interface ScreenSpec {
  /** Frame width in px. Mobile: 393. */
  width: number;
  /**
   * REQUIRED. Declares HOW the agent decided what to build. Validated at
   * build_from_spec entry — missing or invalid format causes the tool
   * to reject the call. Forces RULE 1 compliance at code level.
   *
   * Format: "<kind>:<detail>" where <kind> is one of:
   *   - wireframe:<nodeId>    — wireframe attached, RULE 0 applies
   *   - skill:<skillId>       — verified skill match (docs/skills/<id>/spec.json)
   *   - form:<key=val,…>      — user answered question form (RULE 1 mode B)
   *   - skip:<reason>         — user explicit "just build, skip questions"
   *
   * Examples:
   *   "wireframe:16805:68746"
   *   "skill:imin-notification-center"
   *   "form:output=notification,mode=mixed,activeTab=all"
   *   "skip:tweak-only follow-up"
   */
  discoverySource: string;
  /** Optional figma node ID — new screen is placed to its right. */
  positionRelativeTo?: string;
  /**
   * @deprecated IGNORED. Wrapper bg is always bg-primary by absolute project rule.
   * Cards/sections inside the wrapper handle their own bg-secondary/bg-tertiary hierarchy.
   */
  bgVar?: 'bg-primary' | 'bg-secondary' | 'bg-tertiary';
  /** Whether to prepend the device Status Bar instance. Default true. */
  statusBar?: boolean;
  /** Normal-flow sections in order. */
  sections: SectionSpec[];
  /** ABSOLUTE-positioned bottom overlays (TabBar above, FAB above TabBar). */
  overlays?: OverlaySpec[];
}
