#include <stdio.h>

int main(void) {
    double balance = 1000.0
    double rate = 0.05;
    int years = 5;
    int year;
    for (year = 1; year <= years; year++) {
        balance = balance + balance * rate;
        printf("year %d: %f\n", year, balance);
    }
    if (balance > 1200.0) {
        printf("goal reached\n");
    }
    printf("final balance %f\n", balance);
    return 0;
}
