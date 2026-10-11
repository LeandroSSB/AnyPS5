#include "prx/libc/include/general/VabiMacros.hpp"
#include <chrono>
#include <cstdint>
#include <cstdlib>
struct PollDescriptor {
    int descriptor;
    short events;
    short revents;
};
extern "C" {
int APS5_VABI socket_nid_postfix(int, int, int);
int APS5_VABI pipe_nid_postfix(int*);
std::int64_t APS5_VABI write_nid_postfix(int, const char*, std::int64_t);
int APS5_VABI close_nid_postfix(int);
int APS5_VABI poll_nid_postfix(PollDescriptor*, std::uint32_t, int);
}
static void Require(bool value) { if (!value) std::abort(); }
constexpr short In = 0x1;
constexpr short Out = 0x4;
constexpr short Hup = 0x10;
constexpr short Invalid = 0x20;
constexpr int FirstSocket = 0x10000000;
int main() {
    int pipe[2];
    Require(pipe_nid_postfix(pipe) == 0);
    Require(pipe[0] >= 0 && pipe[0] < FirstSocket && pipe[1] >= 0 && pipe[1] < FirstSocket);
    PollDescriptor reader{pipe[0], In, -1};
    Require(poll_nid_postfix(&reader, 1, 0) == 0 && reader.revents == 0);
    const auto start = std::chrono::steady_clock::now();
    Require(poll_nid_postfix(&reader, 1, 50) == 0);
    Require(std::chrono::steady_clock::now() - start >= std::chrono::milliseconds(40));
    PollDescriptor writer{pipe[1], Out, -1};
    Require(poll_nid_postfix(&writer, 1, 0) == 1 && writer.revents == Out);
    const int socket = socket_nid_postfix(2, 2, 0);
    Require(socket >= FirstSocket);
    PollDescriptor mixed[2]{{pipe[0], In, -1}, {socket, In, -1}};
    const auto mixedStart = std::chrono::steady_clock::now();
    Require(poll_nid_postfix(mixed, 2, 50) == 0);
    Require(std::chrono::steady_clock::now() - mixedStart >= std::chrono::milliseconds(40));
    Require(mixed[0].revents == 0 && mixed[1].revents == 0);
    const char message[] = "poll";
    Require(write_nid_postfix(pipe[1], message, sizeof(message)) == static_cast<std::int64_t>(sizeof(message)));
    mixed[0] = {pipe[0], In, -1};
    mixed[1] = {socket, In, -1};
    Require(poll_nid_postfix(mixed, 2, 1000) == 1);
    Require(mixed[0].revents == In && mixed[1].revents == 0);
    Require(close_nid_postfix(socket) == 0);
#ifndef _WIN32
    Require(close_nid_postfix(pipe[1]) == 0);
    PollDescriptor hung{pipe[0], In, -1};
    Require(poll_nid_postfix(&hung, 1, 1000) == 1 && (hung.revents & Hup) != 0);
#endif
    Require(close_nid_postfix(pipe[0]) == 0);
    PollDescriptor closed{pipe[0], In, -1};
    Require(poll_nid_postfix(&closed, 1, 0) == 1 && closed.revents == Invalid);
#ifdef _WIN32
    Require(close_nid_postfix(pipe[1]) == 0);
#endif
}
