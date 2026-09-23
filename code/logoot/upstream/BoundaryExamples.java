package jbenchmarker.logoot;

import crdt.Operation;
import java.lang.reflect.Field;
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Random;

/** Fixtures for the unmodified coast-team allocator and identifier classes. */
public class BoundaryExamples {
    private static class Site implements TimestampedDocument {
        private final int id;
        private int clock;

        Site(int id) { this.id = id; }
        public int getReplicaNumber() { return id; }
        public int nextClock() { return ++clock; }
        public String view() { throw new UnsupportedOperationException(); }
        public int viewLength() { throw new UnsupportedOperationException(); }
        public void apply(Operation operation) { throw new UnsupportedOperationException(); }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    @SuppressWarnings("unchecked")
    private static int compare(ListIdentifier left, ListIdentifier right) {
        return left.compareTo(right);
    }

    private static void seed(long value) throws Exception {
        Field field = RandomLogootStrategy.class.getDeclaredField("ran");
        field.setAccessible(true);
        field.set(null, new Random(value));
    }

    private static void checkBetween(ListIdentifier left, ListIdentifier value, ListIdentifier right) {
        require(compare(left, value) < 0 && compare(value, right) < 0,
                "Allocation outside interval: " + left + " < " + value + " < " + right);
    }

    private static void boundaryList() throws Exception {
        seed(0);
        for (int bits : new int[] {8, 16, 32}) {
            BoundaryListStrategy strategy = new BoundaryListStrategy(bits);
            LogootListPosition left = new LogootListPosition(bits, 1, 1, 1);
            LogootListPosition right = new LogootListPosition(bits, 1, 2, 1);
            left.set(0, 1);
            right.set(0, 1);
            // Same primary digit, different site metadata in the packed position.
            require(left.getSafe(0) == right.getSafe(0), "Expected equal primary digits");
            require(left.getSafe(1) != right.getSafe(1), "Site metadata must end the equality scan");
            for (int site = 0; site < 10; site++) {
                Site document = new Site(site);
                for (int i = 0; i < 100; i++) {
                    ListIdentifier value = strategy.generateLineIdentifiers(document, left, right, 1).get(0);
                    checkBetween(left, value, right);
                }
            }
            System.out.println("BoundaryListStrategy " + bits + " bits: " + left + " < " + right
                    + "; 1000 allocations strictly between, no hang");
        }
    }

    private static ListIdentifier insert(BoundaryStrategy strategy, Site document,
            List<ListIdentifier> state, int index, String expected) {
        ListIdentifier left = state.get(index - 1), right = state.get(index);
        ListIdentifier value = strategy.generateLineIdentifiers(document, left, right, 1).get(0);
        checkBetween(left, value, right);
        require(value.toString().equals(expected), "Unexpected fixture allocation: " + value);
        state.add(index, value);
        System.out.println("Site " + document.id + " inserts " + value + " between " + left + " and " + right);
        return value;
    }

    private static void boundary() throws Exception {
        seed(80);
        BoundaryStrategy strategy = new BoundaryStrategy(4, 1000000000L);
        Site a = new Site(1), b = new Site(2);
        List<ListIdentifier> stateA = new ArrayList<>(Arrays.asList(strategy.begin(), strategy.end()));
        insert(strategy, a, stateA, 1, "<5,1,1>");
        // B receives the first insertion, then both clients edit concurrently.
        List<ListIdentifier> stateB = new ArrayList<>(stateA);
        ListIdentifier sixA = insert(strategy, a, stateA, 2, "<6,1,2>");
        ListIdentifier sixB = insert(strategy, b, stateB, 2, "<6,2,1>");
        ListIdentifier tail = insert(strategy, a, stateA, 3, "<6,1,2><7,1,3>");
        require(stateA.remove(sixA), "Delete A's 6");
        ListIdentifier lower = insert(strategy, a, stateA, 2, "<5,1,1><10,1,4>");
        // B's only dependency was the shared first insertion. Delivery to A is causal.
        checkBetween(tail, sixB, strategy.end());
        stateA.add(stateA.size() - 1, sixB);
        require(stateA.remove(tail), "Delete A's extension of 6");
        require(stateA.get(2).equals(lower) && stateA.get(3).equals(sixB), "Expected adjacent endpoints");
        System.out.println("After A's deletions and delivery from B: " + stateA);

        LogootIdentifier left = (LogootIdentifier) lower, right = (LogootIdentifier) sixB;
        require(right.getDigitAt(0) - left.getDigitAt(0) - 1 == 0, "Initial interval must be zero");
        require(left.length() == 2 && right.length() == 1, "All subsequent digits must be zero");
        BigInteger interval = BigInteger.valueOf(7 - left.getDigitAt(1) + right.getDigitAt(1));
        require(interval.equals(BigInteger.valueOf(-3)), "First widened interval must be -3");
        // Upstream uses base=16 but max=7. After this depth d_next=16*d+7.
        // For every negative integer d, 16*d+7 < d < 1, so the loop cannot finish.
        for (int i = 0; i < 5; i++) {
            System.out.println("Widened interval: " + interval);
            BigInteger next = interval.multiply(BigInteger.valueOf(16)).add(BigInteger.valueOf(7));
            require(next.compareTo(interval) < 0 && next.signum() < 0, "Expected decreasing negative interval");
            interval = next;
        }
        System.out.println("CALLING_NONTERMINATING_ALLOCATION");
        System.out.flush();
        strategy.generateLineIdentifiers(a, left, right, 1);
        throw new AssertionError("Expected allocation never to return");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("list")) boundaryList();
        else if (args.length == 1 && args[0].equals("boundary")) boundary();
        else throw new IllegalArgumentException("Expected list or boundary");
    }
}
