#include <stdio.h>

struct Flags {
    int ready : 1;
    int count;
};

int main(void) {
    struct Flags f;
    struct Flags g;
    f.count = 3;
    g.count = f.count + 1;
    f.count += g.count;
    printf("%d %d\n", f.count, g.count);
    return 0;
}
