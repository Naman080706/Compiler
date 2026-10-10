#include <stdio.h>

int percent(int present, int total) {
    return present * 100 / total;
}

void show(int pct) {
    printf("attendance: %d%%\n", pct);
}

int main(void) {
    int days[3];
    int present = 0;
    int i;
    int pct;
    int check;
    days[0] = 18;
    days[1] = 20;
    days[2] = 17;
    for (i = 0; i < 3; i++) {
        present += days[i];
    }
    pct = show(percent(present, 60));
    check = percent(present, "sixty");
    printf("pct %d, check %d\n", pct, check);
    return 0;
}
