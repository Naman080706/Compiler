#include <stdio.h>

int half_of(int n) {
    int h = n / 2.0;
    return h;
}

int main(void) {
    int count = "ten";
    int i;
    for (i = 0; i < count; i++) {
        printf("half of %d is %d\n", i, half_of(i));
    }
    return 0;
}
